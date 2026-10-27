"""تنبيهات الوظائف في البريد (لينكدإن، جدارات، بيت، Indeed...).

الطريقة النظامية لجلب وظائف لينكدإن: فعّل تنبيهات الوظائف في حسابك،
وهذه الوحدة تقرأ رسائل التنبيه من بريدك وتستخرج الوظائف وروابطها.
"""
from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from ..config import settings
from .base import CollectorError, RawJob, html_to_text, normalize_url

JOB_LINK_PATTERNS = [
    re.compile(r"linkedin\.com/(comm/)?jobs/view/\d+"),
    re.compile(r"jadarat\.sa"),
    re.compile(r"bayt\.com/.+/jobs/"),
    re.compile(r"indeed\.com/(rc/clk|viewjob|pagead)"),
    re.compile(r"/jobs?/"),
]
NOISE_TEXT = {"view job", "apply", "عرض الوظيفة", "تقدم الآن", "see all jobs", "unsubscribe"}


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _html_part(msg: email.message.Message) -> str:
    html, plain = "", ""
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_maintype() == "multipart":
            continue
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if ctype == "text/html":
            html += text
        elif ctype == "text/plain":
            plain += text
    return html or f"<pre>{plain}</pre>"


def parse_alert_email(html: str, sender: str, received: datetime | None) -> list[RawJob]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: dict[str, RawJob] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not any(p.search(href) for p in JOB_LINK_PATTERNS):
            continue
        title = a.get_text(" ", strip=True)
        if len(title) < 4 or title.lower() in NOISE_TEXT:
            continue
        url = normalize_url(href) or href
        if url in jobs:
            continue
        # السطور المجاورة في نفس الخلية عادةً: الشركة ثم المدينة
        container = a.find_parent(["td", "div", "li"]) or a.parent
        context = html_to_text(str(container)) if container else ""
        lines = [ln for ln in context.splitlines() if ln and ln != title]
        jobs[url] = RawJob(
            title=title[:300],
            description=context[:3000],
            url=url,
            company=lines[0][:200] if lines else None,
            location=lines[1][:200] if len(lines) > 1 else None,
            posted_at=received,
            extra={"via": sender},
        )
    return list(jobs.values())


def collect(config: dict) -> list[RawJob]:
    if not (settings.imap_user and settings.imap_password):
        raise CollectorError("اضبط IMAP_USER و IMAP_PASSWORD في ملف .env لقراءة تنبيهات البريد")
    senders = config.get("senders") or ["jobalerts-noreply@linkedin.com"]
    days = int(config.get("days", 3))
    folder = config.get("folder", "INBOX")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
    out: list[RawJob] = []
    try:
        conn = imaplib.IMAP4_SSL(settings.imap_host)
        conn.login(settings.imap_user, settings.imap_password)
        conn.select(folder, readonly=True)
        for sender in senders:
            sender = re.sub(r"[^A-Za-z0-9@._+-]", "", sender)
            if not sender:
                continue
            status, data = conn.search(None, f'(FROM "{sender}" SINCE {since})')
            if status != "OK":
                continue
            for num in data[0].split()[-50:]:
                status, msg_data = conn.fetch(num, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                try:
                    received = parsedate_to_datetime(msg.get("Date"))
                except (TypeError, ValueError):
                    received = None
                out.extend(parse_alert_email(_html_part(msg), _decode(msg.get("From")), received))
        conn.logout()
    except imaplib.IMAP4.error as e:
        raise CollectorError(f"فشل الدخول للبريد: {e}") from e
    except OSError as e:
        raise CollectorError(f"تعذر الاتصال بخادم البريد: {e}") from e
    return out
