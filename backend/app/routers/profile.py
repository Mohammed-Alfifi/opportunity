import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import mailer, services
from ..analysis import llm
from ..config import settings
from ..db import get_session
from ..schemas import ProfileIO

router = APIRouter(prefix="/api", tags=["profile"])
MAX_CV_BYTES = 8 * 1024 * 1024


@router.get("/profile", response_model=ProfileIO)
def get_profile(session: Session = Depends(get_session)):
    return services.get_profile(session)


@router.put("/profile", response_model=ProfileIO)
def put_profile(data: ProfileIO, session: Session = Depends(get_session)):
    p = services.get_profile(session)
    clean = lambda xs: [x.strip() for x in xs if x and x.strip()]  # noqa: E731
    for k, v in data.model_dump(exclude={"cv_filename"}).items():
        setattr(p, k, clean(v) if isinstance(v, list) else v)
    session.commit()
    services.rescore_all(session)
    return p


@router.post("/profile/cv", response_model=ProfileIO)
async def upload_cv(file: UploadFile = File(...), session: Session = Depends(get_session)):
    data = await file.read()
    if len(data) > MAX_CV_BYTES:
        raise HTTPException(413, "الملف أكبر من 8 ميجابايت")
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "ارفع السيرة الذاتية بصيغة PDF")
    p = services.get_profile(session)
    p.cv_data = data
    p.cv_filename = file.filename or "CV.pdf"
    try:
        from pypdf import PdfReader

        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(data)).pages)
        if text.strip():
            p.cv_text = text.strip()[:20000]
    except Exception:  # noqa: BLE001
        pass
    session.commit()
    services.rescore_all(session)
    return p


@router.get("/status")
def status(session: Session = Depends(get_session)):
    from sqlalchemy import select

    from ..models import Profile

    has_cv = session.scalar(select(Profile.id).where(Profile.id == 1, Profile.cv_data.is_not(None))) is not None
    return {
        "llm": {"enabled": llm.enabled(), "provider": settings.llm_provider, "model": settings.llm_model},
        "smtp": {"configured": mailer.configured(), "user": mailer.sender_label(), "transport": settings.mail_transport},
        "imap": {"configured": bool(settings.imap_user and settings.imap_password)},
        "cv_uploaded": has_cv,
        "collect_interval_minutes": settings.collect_interval_minutes if settings.scheduler_enabled else None,
    }
