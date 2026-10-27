"""إعدادات المنصة من متغيرات البيئة (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    data_dir: Path = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
    database_url: str = os.getenv("DATABASE_URL", "")
    cors_origins: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
    ]

    # النشر العام: كلمة مرور الدخول، مفتاح توقيع الجلسات، ورمز المهمة المجدولة الخارجية
    environment: str = os.getenv("ENVIRONMENT", "local").lower()  # local | production
    app_password: str = os.getenv("APP_PASSWORD", "")
    secret_key: str = os.getenv("SECRET_KEY", "")
    cron_token: str = os.getenv("CRON_TOKEN", "")
    session_hours: int = int(os.getenv("SESSION_HOURS", "168"))
    static_dir: str = os.getenv("STATIC_DIR", "")  # مجلد الواجهة المصدَّرة لخدمتها من نفس الخادم

    # الجمع الدوري
    collect_interval_minutes: int = int(os.getenv("COLLECT_INTERVAL_MINUTES", "60"))
    scheduler_enabled: bool = _bool("SCHEDULER_ENABLED", True)
    http_timeout: float = float(os.getenv("HTTP_TIMEOUT", "20"))
    # للاختبارات أو المصادر داخل شبكتك فقط
    allow_private_network: bool = _bool("ALLOW_PRIVATE_NETWORK", False)
    telegram_base_url: str = os.getenv("TELEGRAM_BASE_URL", "https://t.me/s")
    user_agent: str = os.getenv(
        "USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64) Forsa/1.0 personal job aggregator"
    )

    # نموذج اللغة: none | anthropic | openai | ollama
    llm_provider: str = os.getenv("LLM_PROVIDER", "none").lower()
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")

    # البريد الصادر (Gmail: smtp.gmail.com:587 + كلمة مرور تطبيق)
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    # starttls (587) | ssl (465) | none (خادم محلي للاختبار فقط)
    smtp_security: str = os.getenv("SMTP_SECURITY", "").lower()
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from_name: str = os.getenv("SMTP_FROM_NAME", "")
    # smtp (محلياً) | gas: الإرسال عبر Google Apps Script من حساب Gmail نفسه فوق HTTPS،
    # لأن الاستضافات المجانية (ومنها Render) تحجب منافذ SMTP الصادرة
    mail_transport: str = os.getenv("MAIL_TRANSPORT", "smtp").lower()
    gas_url: str = os.getenv("GAS_URL", "")
    gas_token: str = os.getenv("GAS_TOKEN", "")

    # البريد الوارد لقراءة تنبيهات الوظائف (لينكدإن، جدارات، بيت...)
    imap_host: str = os.getenv("IMAP_HOST", "imap.gmail.com")
    imap_user: str = os.getenv("IMAP_USER", "")
    imap_password: str = os.getenv("IMAP_PASSWORD", "")

    def __init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'forsa.db'}"
        # Neon وRender يعطيان postgres:// أو postgresql://؛ SQLAlchemy يحتاج اسم المشغّل
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                self.database_url = "postgresql+psycopg://" + self.database_url[len(prefix):]
        if self.environment == "production":
            missing = [n for n, v in (("APP_PASSWORD", self.app_password), ("SECRET_KEY", self.secret_key)) if not v]
            if missing:
                raise RuntimeError(f"وضع الإنتاج يتطلب ضبط: {', '.join(missing)}")
            if len(self.app_password) < 12:
                raise RuntimeError("APP_PASSWORD يجب ألا يقل عن 12 حرفاً في وضع الإنتاج")

    @property
    def auth_enabled(self) -> bool:
        return bool(self.app_password)



settings = Settings()
