from . import imap, rss, telegram, webpage
from .base import CollectorError, RawJob

COLLECTORS = {
    "rss": rss.collect,
    "telegram": telegram.collect,
    "webpage": webpage.collect,
    "imap": imap.collect,
}

KIND_LABELS = {
    "rss": "خلاصة RSS (مواقع التوظيف)",
    "telegram": "قناة تيليجرام عامة",
    "webpage": "صفحة وظائف (شركة أو جهة حكومية)",
    "imap": "تنبيهات البريد (لينكدإن، جدارات، بيت)",
}

__all__ = ["COLLECTORS", "KIND_LABELS", "CollectorError", "RawJob", "webpage"]
