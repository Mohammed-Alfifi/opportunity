import logging
import threading

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .. import auth, services
from ..config import settings
from ..db import SessionLocal

router = APIRouter(prefix="/api", tags=["auth"])
log = logging.getLogger("forsa.auth")
_collect_lock = threading.Lock()


class LoginIn(BaseModel):
    password: str


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/auth/me")
def me(request: Request):
    if not settings.auth_enabled:
        return {"auth_required": False, "authenticated": True}
    return {"auth_required": True, "authenticated": auth.valid_token(request.cookies.get(auth.COOKIE))}


@router.post("/auth/login")
def login(data: LoginIn, request: Request, response: Response):
    if not settings.auth_enabled:
        return {"ok": True}
    ip = client_ip(request)
    wait = auth.blocked(ip)
    if wait:
        raise HTTPException(429, f"محاولات كثيرة. حاول بعد {wait // 60 + 1} دقيقة",
                            headers={"Retry-After": str(wait)})
    if not auth.check_password(ip, data.password):
        log.warning("محاولة دخول فاشلة من %s", ip)
        raise HTTPException(401, "كلمة المرور غير صحيحة")
    response.set_cookie(
        auth.COOKIE, auth.make_token(), max_age=settings.session_hours * 3600,
        httponly=True, samesite="lax", secure=settings.environment == "production", path="/",
    )
    return {"ok": True}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


def _collect_job() -> None:
    try:
        with SessionLocal() as session:
            results = services.run_all(session)
            log.info("جمع خارجي: %s وظيفة جديدة", sum(results.values()))
    finally:
        _collect_lock.release()


@router.post("/cron/collect", status_code=202)
def cron_collect(request: Request):
    """تستدعيه مهمة GitHub Actions كل ساعة: يوقظ الخدمة النائمة ويبدأ الجمع في الخلفية."""
    if not auth.valid_cron(request.headers.get("authorization")):
        raise HTTPException(401, "رمز غير صالح")
    if not _collect_lock.acquire(blocking=False):
        return {"started": False, "detail": "جمع سابق ما زال جارياً"}
    threading.Thread(target=_collect_job, daemon=True).start()
    return {"started": True}
