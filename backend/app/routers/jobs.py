from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from .. import services
from ..collectors import CollectorError, RawJob, webpage
from ..collectors.base import extract_email
from ..db import get_session
from ..models import Application, Job
from ..schemas import (ApplicationOut, DraftIn, ImportUrlIn, JobDetail, JobManualIn, JobOut,
                       JobStatus, JobUpdate)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _with_source(j: Job, model=JobOut):
    out = model.model_validate(j)
    out.source_name = j.source.name if j.source else "إضافة يدوية"
    return out


@router.get("", response_model=dict)
def list_jobs(
    session: Session = Depends(get_session),
    status: JobStatus | None = None,
    q: str | None = None,
    min_score: int = 0,
    source_id: int | None = None,
    sort: str = Query("newest", pattern="^(newest|score)$"),
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    stmt = select(Job).options(joinedload(Job.source))
    if status:
        stmt = stmt.where(Job.status == status)
    else:
        stmt = stmt.where(Job.status != "ignored")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company.ilike(like), Job.description.ilike(like)))
    if min_score:
        stmt = stmt.where(Job.score >= min_score)
    if source_id:
        stmt = stmt.where(Job.source_id == source_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = [Job.score.desc().nulls_last(), Job.created_at.desc()] if sort == "score" else [Job.created_at.desc()]
    rows = session.scalars(stmt.order_by(*order).limit(limit).offset(offset)).unique().all()
    return {"total": total, "items": [_with_source(j) for j in rows]}


@router.get("/stats")
def stats(session: Session = Depends(get_session)):
    by_status = dict(session.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    strong = session.scalar(select(func.count()).where(Job.score >= 70, Job.status == "new")) or 0
    sent = session.scalar(select(func.count()).where(Application.status == "sent")) or 0
    return {"by_status": by_status, "strong_new": strong, "sent": sent,
            "total": sum(by_status.values())}


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, session: Session = Depends(get_session)):
    return _with_source(_get(session, job_id), JobDetail)


@router.patch("/{job_id}", response_model=JobDetail)
def update_job(job_id: int, data: JobUpdate, session: Session = Depends(get_session)):
    j = _get(session, job_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(j, k, v)
    session.commit()
    return _with_source(j, JobDetail)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: int, session: Session = Depends(get_session)):
    session.delete(_get(session, job_id))
    session.commit()


@router.post("", response_model=JobDetail, status_code=201)
def add_manual(data: JobManualIn, session: Session = Depends(get_session)):
    raw = RawJob(title=data.title, description=data.description, url=data.url,
                 company=data.company, location=data.location)
    job = services.save_raw_job(session, raw, None, services.get_profile(session))
    if not job:
        raise HTTPException(409, "هذه الوظيفة موجودة مسبقاً")
    if data.contact_email:
        job.contact_email = data.contact_email
    session.commit()
    return _with_source(job, JobDetail)


@router.post("/import-url", response_model=JobDetail, status_code=201)
def import_url(data: ImportUrlIn, session: Session = Depends(get_session)):
    try:
        raw = webpage.import_url(data.url)
    except CollectorError as e:
        raise HTTPException(422, f"{e} — يمكنك إضافة الوظيفة يدوياً بنسخ نصها") from e
    job = services.save_raw_job(session, raw, None, services.get_profile(session))
    if not job:
        raise HTTPException(409, "هذه الوظيفة موجودة مسبقاً")
    job.contact_email = job.contact_email or extract_email(raw.description)
    session.commit()
    return _with_source(job, JobDetail)


@router.post("/{job_id}/analyze", response_model=JobDetail)
def analyze(job_id: int, use_llm: bool = True, session: Session = Depends(get_session)):
    return _with_source(services.analyze_job(session, _get(session, job_id), use_llm), JobDetail)


@router.post("/rescore")
def rescore(session: Session = Depends(get_session)):
    return {"rescored": services.rescore_all(session)}


@router.get("/{job_id}/application", response_model=ApplicationOut | None)
def get_application(job_id: int, session: Session = Depends(get_session)):
    j = _get(session, job_id)
    apps = sorted(j.applications, key=lambda a: a.updated_at, reverse=True)
    return apps[0] if apps else None


@router.post("/{job_id}/application", response_model=ApplicationOut)
def draft(job_id: int, data: DraftIn, session: Session = Depends(get_session)):
    j = _get(session, job_id)
    return services.draft_application(session, j, data.lang, data.use_llm, data.instructions)


def _get(session: Session, job_id: int) -> Job:
    j = session.get(Job, job_id)
    if not j:
        raise HTTPException(404, "الوظيفة غير موجودة")
    return j
