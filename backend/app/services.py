"""منطق الجمع والتحليل والتقديم."""
from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .analysis import analyzer
from .collectors import COLLECTORS, CollectorError, RawJob
from .collectors.base import detect_lang, extract_email, fingerprint, passes_filters, safe_url, valid_email
from .config import settings
from .models import Application, Job, Profile, Source

log = logging.getLogger("forsa")

# الجمع الدوري والجمع اليدوي لا يعملان معاً، حتى لا تتصادم إدخالات نفس الوظيفة
_collect_lock = threading.Lock()


def get_profile(session: Session) -> Profile:
    p = session.get(Profile, 1)
    if not p:
        p = Profile(id=1)
        session.add(p)
        session.commit()
    return p


def profile_dict(p: Profile) -> dict:
    return {c: getattr(p, c) for c in (
        "full_name", "email", "phone", "headline", "summary", "skills", "target_titles",
        "locations", "years_experience", "links", "cv_text")}


def job_dict(j: Job) -> dict:
    return {"title": j.title, "company": j.company, "location": j.location, "description": j.description}


def save_raw_job(session: Session, raw: RawJob, source: Source | None, profile: Profile) -> Job | None:
    fp = fingerprint(raw)
    if session.scalar(select(Job.id).where(Job.fingerprint == fp)):
        return None
    text = f"{raw.title}\n{raw.description}"
    url = safe_url(raw.extra.get("apply_url")) or safe_url(raw.url)
    job = Job(
        source_id=source.id if source else None,
        fingerprint=fp,
        title=raw.title[:500],
        company=(raw.company or None) and raw.company[:300],
        location=(raw.location or None) and raw.location[:300],
        url=url,
        description=raw.description,
        posted_at=raw.posted_at,
        lang=detect_lang(text),
        contact_email=extract_email(text),
    )
    a = analyzer.analyze(job_dict(job), profile_dict(profile), use_llm=False)
    job.score, job.analysis = a["score"], a
    session.add(job)
    return job


def run_source(session: Session, source: Source) -> int:
    with _collect_lock:
        return _run_source(session, source)


def _run_source(session: Session, source: Source) -> int:
    profile = get_profile(session)
    collect = COLLECTORS.get(source.kind)
    source.last_run_at = datetime.now(timezone.utc)
    if not collect:
        source.last_error = f"نوع مصدر غير معروف: {source.kind}"
        session.commit()
        return 0
    try:
        raws = collect(source.config or {})
    except CollectorError as e:
        source.last_error = str(e)
        source.last_new_count = 0
        session.commit()
        return 0
    except Exception as e:  # noqa: BLE001
        log.exception("collector crashed")
        source.last_error = f"خطأ غير متوقع: {e}"
        session.commit()
        return 0
    new = 0
    seen: set[str] = set()
    for raw in raws:
        if not passes_filters(raw, source.config or {}):
            continue
        fp = fingerprint(raw)
        if fp in seen:
            continue
        seen.add(fp)
        try:
            with session.begin_nested():
                if save_raw_job(session, raw, source, profile):
                    session.flush()
                    new += 1
        except IntegrityError:
            log.info("وظيفة مكررة أُدخلت من عملية أخرى، تم تجاهلها")
    source.last_error = None
    source.last_new_count = new
    session.commit()
    return new


def run_all(session: Session) -> dict:
    results = {}
    for s in session.scalars(select(Source).where(Source.enabled.is_(True))).all():
        results[s.id] = run_source(session, s)
    return results


def rescore_all(session: Session) -> int:
    profile = profile_dict(get_profile(session))
    jobs = session.scalars(select(Job).where(Job.status.in_(["new", "shortlisted"]))).all()
    for j in jobs:
        if (j.analysis or {}).get("engine") == "llm":
            continue
        a = analyzer.analyze(job_dict(j), profile, use_llm=False)
        j.score, j.analysis = a["score"], a
    session.commit()
    return len(jobs)


def analyze_job(session: Session, job: Job, use_llm: bool = True) -> Job:
    a = analyzer.analyze(job_dict(job), profile_dict(get_profile(session)), use_llm=use_llm)
    job.score, job.analysis = a["score"], a
    if not job.company and isinstance(a.get("company"), str):
        job.company = a["company"][:300]
    if not job.location and isinstance(a.get("location"), str):
        job.location = a["location"][:300]
    session.commit()
    return job


def draft_application(session: Session, job: Job, lang: str | None = None, use_llm: bool = True,
                      instructions: str = "") -> Application:
    profile = get_profile(session)
    letter = analyzer.write_letter(job_dict(job), profile_dict(profile), job.analysis,
                                   lang or job.lang, use_llm=use_llm, instructions=instructions)
    app = next((a for a in job.applications if a.status in ("draft", "failed")), None)
    if not app:
        app = Application(job_id=job.id, to_email=job.contact_email or "")
        session.add(app)
    app.subject, app.body, app.status, app.error = letter["subject"], letter["body"], "draft", letter.get("llm_error")
    session.commit()
    session.refresh(app)
    return app


def send_application(session: Session, app: Application) -> Application:
    from . import mailer

    if app.status in ("sent", "sending"):
        raise mailer.MailError("تم إرسال هذا التقديم مسبقاً أو أن إرساله جارٍ")
    if not valid_email(app.to_email):
        raise mailer.MailError("أدخل بريد جهة التوظيف قبل الإرسال")
    profile = get_profile(session)
    attachment = profile.cv_data if app.attach_cv else None
    if app.attach_cv and not attachment:
        raise mailer.MailError("ارفع سيرتك الذاتية (PDF) من صفحة الملف الشخصي أو ألغِ خيار الإرفاق")
    msg = mailer.build_message(
        to=app.to_email, subject=app.subject, body=app.body,
        from_name=settings.smtp_from_name or profile.full_name,
        reply_to=profile.email or None, attachment=attachment,
        attachment_name=profile.cv_filename or "CV.pdf",
    )
    # حجز ذري: ضغطتان متتاليتان على "أرسل" لا ترسلان رسالتين
    claimed = session.execute(
        update(Application).where(Application.id == app.id, Application.status.in_(["draft", "failed"]))
        .values(status="sending")
    ).rowcount
    session.commit()
    if not claimed:
        session.refresh(app)
        raise mailer.MailError("تم إرسال هذا التقديم مسبقاً أو أن إرساله جارٍ")
    session.refresh(app)
    try:
        # مفتاح ثابت لنفس المحتوى: إعادة المحاولة بعد انقطاع لا ترسل نسخة ثانية (في وضع gas)
        digest = hashlib.sha256(f"{app.to_email}\n{app.subject}\n{app.body}".encode()).hexdigest()[:20]
        mailer.send(msg, key=f"forsa-{app.id}-{digest}")
    except Exception as e:  # noqa: BLE001 - أي فشل يعيد التقديم لحالة يمكن إعادة المحاولة منها
        app.status, app.error = "failed", str(e)
        session.commit()
        if isinstance(e, mailer.MailError):
            raise
        raise mailer.MailError(f"فشل الإرسال: {e}") from e
    app.status, app.error, app.sent_at = "sent", None, datetime.now(timezone.utc)
    app.job.status = "applied"
    session.commit()
    return app
