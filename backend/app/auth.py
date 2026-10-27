"""الدخول بكلمة مرور واحدة (منصة شخصية لمستخدم واحد) عبر كوكي موقّع بـ HMAC.

- لا تُفعَّل الحماية إلا عند ضبط APP_PASSWORD (التشغيل المحلي يبقى كما هو).
- مفتاح التوقيع مشتق من SECRET_KEY + كلمة المرور: تغيير كلمة المرور يُبطل كل الجلسات القائمة.
- محاولات الدخول الخاطئة محدودة لكل عنوان وعلى مستوى الخادم كله ضد التخمين الموزّع.
"""
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from .config import settings

COOKIE = "forsa_session"
WINDOW = 15 * 60
MAX_PER_IP = 5
MAX_GLOBAL = 30

_fails: dict[str, deque] = defaultdict(deque)
_global: deque = deque()
_lock = threading.Lock()
# في التشغيل المحلي بلا SECRET_KEY نولّد مفتاحاً مؤقتاً (الجلسات تنتهي بإعادة التشغيل)
_ephemeral = secrets.token_hex(32)


def _key() -> bytes:
    base = settings.secret_key or _ephemeral
    return hashlib.sha256(f"{base}\x00{settings.app_password}".encode()).digest()


def _sign(payload: str) -> str:
    return hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(now: float | None = None) -> str:
    exp = int((now or time.time()) + settings.session_hours * 3600)
    payload = f"v1.{exp}"
    return f"{payload}.{_sign(payload)}"


def valid_token(token: str | None, now: float | None = None) -> bool:
    if not token:
        return False
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1" or not parts[1].isdigit():
        return False
    payload = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_sign(payload), parts[2]):
        return False
    return int(parts[1]) > (now or time.time())


def _prune(q: deque, now: float) -> None:
    while q and q[0] < now - WINDOW:
        q.popleft()


def blocked(ip: str) -> int:
    """يعيد عدد الثواني المتبقية على رفع الحظر، أو 0 إن كان مسموحاً."""
    now = time.time()
    with _lock:
        q = _fails[ip]
        _prune(q, now)
        _prune(_global, now)
        if len(q) >= MAX_PER_IP:
            return int(q[0] + WINDOW - now) + 1
        if len(_global) >= MAX_GLOBAL:
            return int(_global[0] + WINDOW - now) + 1
    return 0


def check_password(ip: str, password: str) -> bool:
    ok = hmac.compare_digest(password.encode(), settings.app_password.encode())
    now = time.time()
    with _lock:
        if ok:
            _fails.pop(ip, None)
        else:
            _fails[ip].append(now)
            _global.append(now)
    return ok


def valid_cron(header: str | None) -> bool:
    if not settings.cron_token or not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].encode(), settings.cron_token.encode())


def reset_limits() -> None:  # للاختبارات
    with _lock:
        _fails.clear()
        _global.clear()
