from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services
from ..collectors import KIND_LABELS
from ..db import get_session
from ..models import Job, Source
from ..schemas import SourceIn, SourceOut

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _out(session: Session, s: Source) -> SourceOut:
    out = SourceOut.model_validate(s)
    out.job_count = session.scalar(select(func.count(Job.id)).where(Job.source_id == s.id)) or 0
    return out


@router.get("/kinds")
def kinds() -> dict:
    return KIND_LABELS


@router.get("", response_model=list[SourceOut])
def list_sources(session: Session = Depends(get_session)):
    return [_out(session, s) for s in session.scalars(select(Source).order_by(Source.id)).all()]


@router.post("", response_model=SourceOut, status_code=201)
def create_source(data: SourceIn, session: Session = Depends(get_session)):
    s = Source(**data.model_dump())
    session.add(s)
    session.commit()
    return _out(session, s)


@router.put("/{source_id}", response_model=SourceOut)
def update_source(source_id: int, data: SourceIn, session: Session = Depends(get_session)):
    s = session.get(Source, source_id) or _404()
    for k, v in data.model_dump().items():
        setattr(s, k, v)
    session.commit()
    return _out(session, s)


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int, session: Session = Depends(get_session)):
    s = session.get(Source, source_id) or _404()
    session.delete(s)
    session.commit()


@router.post("/{source_id}/run", response_model=SourceOut)
def run_source(source_id: int, session: Session = Depends(get_session)):
    s = session.get(Source, source_id) or _404()
    services.run_source(session, s)
    return _out(session, s)


@router.post("/run-all")
def run_all(session: Session = Depends(get_session)):
    results = services.run_all(session)
    return {"new_jobs": sum(results.values()), "per_source": results}


def _404():
    raise HTTPException(404, "المصدر غير موجود")
