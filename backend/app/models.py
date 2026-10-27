from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, LargeBinary, String, Text, TypeDecorator
from sqlalchemy import DateTime as _DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class DateTime(TypeDecorator):
    """يخزن بتوقيت UTC ويعيده بمنطقة زمنية؛ SQLite تفقدها افتراضياً فتظهر الأوقات خاطئة في المتصفح."""

    impl = _DateTime
    cache_ok = True

    def __init__(self, timezone: bool = True):  # noqa: ARG002
        super().__init__(timezone=True)

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):  # noqa: ANN001
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Source(Base):
    """مصدر وظائف: rss | telegram | webpage | imap"""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    # rss: {url}  telegram: {channel}  webpage: {url}  imap: {senders: [...], folder}
    # الجميع يدعم: include_keywords, exclude_keywords
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_new_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    jobs: Mapped[list["Job"]] = relationship(back_populates="source")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str | None] = mapped_column(String(300), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lang: Mapped[str] = mapped_column(String(5), default="ar")
    contact_email: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # new | shortlisted | applied | ignored
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

    source: Mapped[Source | None] = relationship(back_populates="jobs")
    applications: Mapped[list["Application"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    to_email: Mapped[str] = mapped_column(String(300), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    attach_cv: Mapped[bool] = mapped_column(Boolean, default=True)
    # draft | sent | failed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    job: Mapped[Job] = relationship(back_populates="applications")


class Profile(Base):
    """ملف المتقدم (صف واحد)."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(300), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    headline: Mapped[str] = mapped_column(String(300), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    target_titles: Mapped[list] = mapped_column(JSON, default=list)
    locations: Mapped[list] = mapped_column(JSON, default=list)
    years_experience: Mapped[int] = mapped_column(Integer, default=0)
    links: Mapped[list] = mapped_column(JSON, default=list)
    cv_text: Mapped[str] = mapped_column(Text, default="")
    cv_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # الملف نفسه في قاعدة البيانات: أقراص الاستضافة المجانية تُمسح عند كل إعادة تشغيل
    cv_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    min_score_to_notify: Mapped[int] = mapped_column(Integer, default=60)
