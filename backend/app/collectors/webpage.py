"""صفحات الوظائف وصفحات التوظيف في الشركات والجهات الحكومية.

تقرأ بيانات schema.org JobPosting المضمنة (JSON-LD) التي تنشرها أغلب أنظمة التوظيف،
وتستخدم أيضاً لاستيراد وظيفة واحدة من رابط يلصقه المستخدم (مثل رابط لينكدإن أو جدارات).
"""
import json
from datetime import datetime

from bs4 import BeautifulSoup

from .base import CollectorError, RawJob, first_line_title, html_to_text
from .http import fetch


def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if "@graph" in node:
                    stack.extend(node["@graph"] if isinstance(node["@graph"], list) else [node["@graph"]])
                t = node.get("@type")
                types = t if isinstance(t, list) else [t]
                if "JobPosting" in types:
                    yield node
                elif "ItemList" in types:
                    for item in node.get("itemListElement", []):
                        stack.append(item.get("item", item) if isinstance(item, dict) else item)


def _location(node: dict) -> str | None:
    loc = node.get("jobLocation")
    locs = loc if isinstance(loc, list) else [loc]
    parts = []
    for l in locs:
        if isinstance(l, dict):
            addr = l.get("address", {})
            if isinstance(addr, dict):
                bits = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                bits = [b.get("name") if isinstance(b, dict) else b for b in bits]
                parts.append("، ".join(b for b in bits if b))
            elif isinstance(addr, str):
                parts.append(addr)
    if node.get("jobLocationType") == "TELECOMMUTE":
        parts.append("عن بعد")
    return " / ".join(p for p in parts if p) or None


def _posting_to_job(node: dict, page_url: str) -> RawJob:
    org = node.get("hiringOrganization")
    company = org.get("name") if isinstance(org, dict) else org
    posted = None
    if node.get("datePosted"):
        try:
            posted = datetime.fromisoformat(str(node["datePosted"]).replace("Z", "+00:00"))
        except ValueError:
            posted = None
    return RawJob(
        title=html_to_text(node.get("title", "")) or "وظيفة",
        description=html_to_text(node.get("description", "")),
        url=node.get("url") or page_url,
        company=company,
        location=_location(node),
        posted_at=posted,
        extra={"apply_url": node.get("url")},
    )


def parse_page(html: str, page_url: str) -> list[RawJob]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = [_posting_to_job(n, page_url) for n in _iter_jsonld(soup)]
    return jobs


def parse_single(html: str, page_url: str) -> RawJob:
    """وظيفة واحدة من رابط: JSON-LD إن وُجد، وإلا وسوم Open Graph ونص الصفحة."""
    jobs = parse_page(html, page_url)
    if jobs:
        return jobs[0]
    soup = BeautifulSoup(html, "html.parser")
    og = lambda p: (soup.find("meta", property=p) or {}).get("content")  # noqa: E731
    title = og("og:title") or (soup.title.string if soup.title else None)
    desc = og("og:description") or ""
    for t in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        t.decompose()
    main = soup.find("main") or soup.body or soup
    body = html_to_text(str(main))
    description = desc if len(body) < len(desc) else body[:8000]
    return RawJob(
        title=(title or first_line_title(description)).strip(),
        description=description,
        url=page_url,
        company=og("og:site_name"),
    )


def collect(config: dict) -> list[RawJob]:
    url = config.get("url")
    if not url:
        raise CollectorError("مصدر صفحة الويب يحتاج رابط url")
    jobs = parse_page(fetch(url), url)
    if not jobs:
        raise CollectorError(
            "الصفحة لا تحتوي بيانات JobPosting مقروءة؛ جرّب خلاصة RSS للموقع أو تنبيهات البريد"
        )
    return jobs


def import_url(url: str) -> RawJob:
    return parse_single(fetch(url), url)
