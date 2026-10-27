"""أدوات مشتركة للمجمّعات."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ARABIC_RE = re.compile(r"[؀-ۿ]")
LATIN_RE = re.compile(r"[A-Za-z]")
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                   "trk", "trackingId", "refId", "ref", "fbclid", "gclid", "lipi", "midToken"}
IGNORED_EMAIL_DOMAINS = ("example.com", "linkedin.com", "sentry.io", "wixpress.com")


@dataclass
class RawJob:
    title: str
    description: str = ""
    url: str | None = None
    company: str | None = None
    location: str | None = None
    posted_at: datetime | None = None
    extra: dict = field(default_factory=dict)


class CollectorError(Exception):
    pass


def safe_url(url: str | None) -> str | None:
    """يقبل روابط http/https فقط؛ يمنع javascript: و data: القادمة من إعلانات أو قنوات."""
    if not url:
        return None
    url = url.strip()
    try:
        p = urlparse(url)
    except ValueError:
        return None
    return url if p.scheme in ("http", "https") and p.netloc else None


def valid_email(value: str | None) -> bool:
    return bool(value) and re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value) is not None


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines()]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if not blank and out:
                out.append("")
            blank = True
            continue
        out.append(ln)
        blank = False
    return "\n".join(out).strip()


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(p.query) if k not in TRACKING_PARAMS]
    return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", urlencode(query), ""))


def fingerprint(job: RawJob) -> str:
    """بصمة لمنع التكرار: الرابط إن وُجد، وإلا العنوان + الجهة + بداية الوصف."""
    # رابط التقديم أولاً: منشور تيليجرام وخلاصة RSS لنفس الوظيفة يشيران لنفس رابط الجهة
    candidates = [normalize_url(u) for u in (job.extra.get("apply_url"), job.url)]
    url = next((u for u in candidates if u and "t.me/" not in u), None)
    if url:
        key = url
    else:
        norm = lambda s: re.sub(r"\s+", " ", (s or "").strip().lower())  # noqa: E731
        key = "|".join([norm(job.title), norm(job.company), norm(job.description)[:300]])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def detect_lang(text: str) -> str:
    ar = len(ARABIC_RE.findall(text or ""))
    en = len(LATIN_RE.findall(text or ""))
    return "ar" if ar >= en * 0.4 and ar > 0 else "en"


def extract_email(text: str) -> str | None:
    for m in EMAIL_RE.findall(text or ""):
        m = m.strip(".").lower()
        if not m.endswith(IGNORED_EMAIL_DOMAINS) and not m.startswith(("noreply", "no-reply")):
            return m
    return None


def passes_filters(job: RawJob, config: dict) -> bool:
    hay = f"{job.title}\n{job.description}".lower()
    include = [k.lower() for k in config.get("include_keywords", []) if k.strip()]
    exclude = [k.lower() for k in config.get("exclude_keywords", []) if k.strip()]
    if include and not any(k in hay for k in include):
        return False
    if exclude and any(k in hay for k in exclude):
        return False
    return True


def first_line_title(text: str, limit: int = 140) -> str:
    for ln in (text or "").splitlines():
        ln = re.sub(r"^[\s#*•\-–|🔴🟢📌✅⭐️🔹🔸💼📢]+", "", ln).strip()
        if len(ln) >= 4:
            return ln[:limit]
    return (text or "وظيفة بدون عنوان").strip()[:limit]
