from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .. import mailer, services
from ..db import get_session
from ..models import Application
from ..schemas import ApplicationOut, ApplicationUpdate

router = APIRouter(prefix="/api/applications", tags=["applications"])


def _out(a: Application) -> ApplicationOut:
    out = ApplicationOut.model_validate(a)
    out.job_title, out.job_company = a.job.title, a.job.company
    return out


@router.get("", response_model=list[ApplicationOut])
def list_apps(session: Session = Depends(get_session)):
    rows = session.scalars(
        select(Application).options(joinedload(Application.job)).order_by(Application.updated_at.desc())
    ).all()
    return [_out(a) for a in rows]


@router.patch("/{app_id}", response_model=ApplicationOut)
def update_app(app_id: int, data: ApplicationUpdate, session: Session = Depends(get_session)):
    a = _get(session, app_id)
    if a.status == "sent":
        raise HTTPException(409, "لا يمكن تعديل تقديم أُرسل")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    if data.to_email and not a.job.contact_email:
        a.job.contact_email = data.to_email
    session.commit()
    return _out(a)


@router.post("/{app_id}/send", response_model=ApplicationOut)
def send(app_id: int, session: Session = Depends(get_session)):
    """الإرسال الفعلي — يُستدعى فقط من زر "إرسال" بعد مراجعتك."""
    a = _get(session, app_id)
    try:
        services.send_application(session, a)
    except mailer.MailError as e:
        raise HTTPException(400, str(e)) from e
    return _out(a)


@router.delete("/{app_id}", status_code=204)
def delete_app(app_id: int, session: Session = Depends(get_session)):
    a = _get(session, app_id)
    if a.status == "sent":
        raise HTTPException(409, "التقديم المرسل يبقى في السجل")
    session.delete(a)
    session.commit()


def _get(session: Session, app_id: int) -> Application:
    a = session.get(Application, app_id)
    if not a:
        raise HTTPException(404, "التقديم غير موجود")
    return a
