"""جلب الصفحات بأمان: مهلة زمنية، حد للحجم، ومنع الوصول للشبكة الداخلية (SSRF)."""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from ..config import settings
from .base import CollectorError

MAX_BYTES = 5 * 1024 * 1024


def _check_host(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise CollectorError(f"رابط غير مدعوم: {url}")
    if settings.allow_private_network:
        return
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror as e:
        raise CollectorError(f"تعذر العثور على النطاق {p.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise CollectorError(f"الرابط يشير إلى عنوان داخلي ({ip}) ولن يُجلب")


def fetch(url: str) -> str:
    _check_host(url)
    try:
        with httpx.Client(
            timeout=settings.http_timeout,
            follow_redirects=True,
            max_redirects=5,
            headers={"User-Agent": settings.user_agent, "Accept-Language": "ar,en;q=0.8"},
            event_hooks={"request": [lambda req: _check_host(str(req.url))]},
        ) as client:
            with client.stream("GET", url) as r:
                r.raise_for_status()
                chunks, size = [], 0
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise CollectorError(f"الصفحة أكبر من {MAX_BYTES // 1024 // 1024} ميجابايت: {url}")
                    chunks.append(chunk)
                return b"".join(chunks).decode(r.encoding or "utf-8", errors="replace")
    except httpx.HTTPStatusError as e:
        raise CollectorError(f"الخادم رد بالحالة {e.response.status_code} على {url}") from e
    except httpx.HTTPError as e:
        raise CollectorError(f"تعذر الوصول إلى {url}: {e}") from e
