"""مواقع التوظيف وصفحات الشركات التي تنشر خلاصة RSS/Atom."""
from datetime import datetime, timezone

import feedparser

from .base import CollectorError, RawJob, html_to_text
from .http import fetch


def parse_feed(xml: str) -> list[RawJob]:
    feed = feedparser.parse(xml)
    if feed.bozo and not feed.entries:
        raise CollectorError("الخلاصة غير صالحة أو فارغة")
    jobs = []
    for e in feed.entries:
        posted = None
        if getattr(e, "published_parsed", None):
            posted = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        desc = e.get("summary") or ""
        if e.get("content"):
            desc = e.content[0].get("value", desc)
        jobs.append(
            RawJob(
                title=html_to_text(e.get("title", "")) or "وظيفة",
                description=html_to_text(desc),
                url=e.get("link"),
                company=e.get("author") or None,
                posted_at=posted,
            )
        )
    return jobs


def collect(config: dict) -> list[RawJob]:
    url = config.get("url")
    if not url:
        raise CollectorError("مصدر RSS يحتاج رابط url")
    return parse_feed(fetch(url))
