import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, services
from .config import settings
from .db import SessionLocal, init_db
from .routers import applications, jobs, profile, sources
from .routers import auth as auth_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("forsa")


def scheduled_collect() -> None:
    if not auth_router._collect_lock.acquire(blocking=False):
        return
    try:
        with SessionLocal() as session:
            results = services.run_all(session)
            log.info("جمع دوري: %s وظيفة جديدة", sum(results.values()))
    finally:
        auth_router._collect_lock.release()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = BackgroundScheduler(timezone="Asia/Riyadh")
        scheduler.add_job(scheduled_collect, "interval", minutes=settings.collect_interval_minutes,
                          id="collect", max_instances=1, coalesce=True)
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


_prod = settings.environment == "production"
# توثيق الـ API مخفي في الإنتاج: لا داعي لكشف شكل الواجهة للعامة
app = FastAPI(title="Forsa API", version="1.2.0", lifespan=lifespan,
              docs_url=None if _prod else "/docs", redoc_url=None, openapi_url=None if _prod else "/openapi.json")

CLIENT_HEADER = "x-forsa-client"
# مسارات لا تتطلب جلسة دخول: الفحص الصحي، الدخول نفسه، ومهمة الجمع المحمية برمزها الخاص
PUBLIC_API = {"/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/me", "/api/cron/collect"}


@app.middleware("http")
async def require_client_header(request: Request, call_next):
    """حماية CSRF: أي صفحة أخرى تفتحها في متصفحك تستطيع إرسال POST بسيط إلى localhost.
    اشتراط ترويسة مخصصة يجبر المتصفح على طلب إذن CORS مسبق، ولا يُمنح إلا لواجهة فرصة."""
    if (request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path != "/api/cron/collect"
            and request.headers.get(CLIENT_HEADER) != "web"):
        return JSONResponse({"detail": "طلب مرفوض: مصدر غير موثوق"}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def require_login(request: Request, call_next):
    """عند ضبط APP_PASSWORD: كل واجهات /api تتطلب كوكي جلسة صالحاً. صفحات الواجهة الثابتة عامة
    لكنها لا تعرض أي بيانات دون الـ API، فتظهر صفحة الدخول."""
    path = request.url.path
    if (settings.auth_enabled and request.method != "OPTIONS" and path.startswith("/api/")
            and path not in PUBLIC_API and not auth.valid_token(request.cookies.get(auth.COOKIE))):
        return JSONResponse({"detail": "يلزم تسجيل الدخول"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if settings.environment == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["content-type", CLIENT_HEADER], allow_credentials=True,
)
for r in (auth_router.router, jobs.router, sources.router, applications.router, profile.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


# الواجهة المصدَّرة (next build بوضع export) تُخدم من نفس الأصل: لا CORS ولا خدمة ثانية
if settings.static_dir:
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="web")
