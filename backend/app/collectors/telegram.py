"""قنوات تيليجرام العامة عبر صفحة المعاينة t.me/s/<channel> (بدون تسجيل دخول)."""
from datetime import datetime

from bs4 import BeautifulSoup

from ..config import settings
from .base import CollectorError, RawJob, first_line_title, html_to_text
from .http import fetch


def channel_url(channel: str) -> str:
    ch = channel.strip().removeprefix("@")
    for prefix in ("https://t.me/s/", "https://t.me/", "http://t.me/", "t.me/"):
        ch = ch.removeprefix(prefix)
    return f"{settings.telegram_base_url.rstrip('/')}/{ch.strip('/')}"


def parse_channel(html: str) -> list[RawJob]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for msg in soup.select(".tgme_widget_message"):
        body = msg.select_one(".tgme_widget_message_text")
        if not body:
            continue
        text = html_to_text(str(body))
        if len(text) < 30:
            continue
        link = msg.select_one("a.tgme_widget_message_date")
        time_el = msg.select_one("time[datetime]")
        posted = None
        if time_el:
            try:
                posted = datetime.fromisoformat(time_el["datetime"])
            except ValueError:
                posted = None
        # أول رابط خارجي في الرسالة غالباً هو رابط التقديم
        apply_link = next(
            (a["href"] for a in body.select("a[href]") if "t.me" not in a["href"]), None
        )
        jobs.append(
            RawJob(
                title=first_line_title(text),
                description=text,
                url=link["href"] if link else None,
                posted_at=posted,
                extra={"apply_url": apply_link},
            )
        )
    return jobs


def collect(config: dict) -> list[RawJob]:
    channel = config.get("channel")
    if not channel:
        raise CollectorError("مصدر تيليجرام يحتاج اسم القناة channel")
    jobs = parse_channel(fetch(channel_url(channel)))
    if not jobs:
        raise CollectorError("لم أجد رسائل؛ تأكد أن القناة عامة وأن اسمها صحيح")
    return jobs
