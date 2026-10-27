from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .collectors.base import safe_url, valid_email


def _email_or_empty(v: str | None) -> str | None:
    if v is None:
        return v
    v = v.strip()
    if v and not valid_email(v):
        raise ValueError("بريد إلكتروني غير صالح")
    return v


def _url_or_empty(v: str | None) -> str | None:
    if not v or not v.strip():
        return None
    if not safe_url(v):
        raise ValueError("الرابط يجب أن يبدأ بـ http أو https")
    return v.strip()


def _required_url(v: str) -> str:
    out = _url_or_empty(v)
    if not out:
        raise ValueError("أدخل رابط الإعلان")
    return out


def _single_line(v: str | None) -> str | None:
    if v is None:
        return v
    if "\r" in v or "\n" in v:
        raise ValueError("الموضوع يجب أن يكون سطراً واحداً")
    return v


Email = Annotated[str, AfterValidator(_email_or_empty)]
OptEmail = Annotated[str | None, AfterValidator(_email_or_empty)]
OptUrl = Annotated[str | None, AfterValidator(_url_or_empty)]
SourceKind = Literal["rss", "telegram", "webpage", "imap"]
JobStatus = Literal["new", "shortlisted", "applied", "ignored"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: SourceKind
    config: dict = {}
    enabled: bool = True


class SourceOut(ORM):
    id: int
    name: str
    kind: str
    config: dict
    enabled: bool
    last_run_at: datetime | None
    last_error: str | None
    last_new_count: int
    job_count: int = 0


class JobOut(ORM):
    id: int
    source_id: int | None
    source_name: str | None = None
    title: str
    company: str | None
    location: str | None
    url: str | None
    posted_at: datetime | None
    lang: str
    contact_email: str | None
    status: str
    score: int | None
    created_at: datetime


class JobDetail(JobOut):
    description: str
    analysis: dict | None


class JobManualIn(BaseModel):
    title: str = Field(min_length=2)
    description: str = ""
    company: str | None = None
    location: str | None = None
    url: OptUrl = None
    contact_email: OptEmail = None


class JobUpdate(BaseModel):
    status: JobStatus | None = None
    contact_email: OptEmail = None
    company: str | None = None
    location: str | None = None


class ImportUrlIn(BaseModel):
    url: Annotated[str, AfterValidator(_required_url)]


class DraftIn(BaseModel):
    lang: Literal["ar", "en"] | None = None
    use_llm: bool = True
    instructions: str = ""


class ApplicationOut(ORM):
    id: int
    job_id: int
    to_email: str
    subject: str
    body: str
    attach_cv: bool
    status: str
    error: str | None
    sent_at: datetime | None
    updated_at: datetime
    job_title: str | None = None
    job_company: str | None = None


class ApplicationUpdate(BaseModel):
    to_email: OptEmail = None
    subject: Annotated[str | None, AfterValidator(_single_line), Field(max_length=300)] = None
    body: str | None = None
    attach_cv: bool | None = None


class ProfileIO(ORM):
    full_name: str = ""
    email: Email = ""
    phone: str = Field("", max_length=40)
    headline: str = ""
    summary: str = ""
    skills: list[str] = []
    target_titles: list[str] = []
    locations: list[str] = []
    years_experience: int = Field(0, ge=0, le=60)
    links: list[str] = []
    cv_text: str = ""
    cv_filename: str | None = None
    min_score_to_notify: int = Field(60, ge=0, le=100)
