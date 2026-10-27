from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
# pool_pre_ping: Neon يغلق الاتصالات الخاملة، فنتحقق قبل كل استخدام
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    _upgrade_schema()


def _upgrade_schema() -> None:
    """ترقية بسيطة لقواعد بيانات أُنشئت بإصدار أقدم (create_all لا يضيف أعمدة لجداول قائمة)."""
    from sqlalchemy import inspect, text

    cols = {c["name"] for c in inspect(engine).get_columns("profile")}
    if "cv_data" not in cols:
        blob = "BYTEA" if engine.dialect.name == "postgresql" else "BLOB"
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE profile ADD COLUMN cv_data {blob}"))
    # نقل ملف السيرة القديم من القرص إلى قاعدة البيانات مرة واحدة
    legacy = settings.data_dir / "cv.pdf"
    if legacy.exists():
        with engine.begin() as conn:
            conn.execute(text("UPDATE profile SET cv_data = :d WHERE id = 1 AND cv_data IS NULL"),
                         {"d": legacy.read_bytes()})
