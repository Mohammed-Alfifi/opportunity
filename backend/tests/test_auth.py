"""اختبارات الحماية للنشر العام: الدخول، الجلسات، التحديد، مهمة الجمع، وتخزين السيرة في القاعدة."""
import time

import pytest

from app import auth
from app.config import Settings, settings

PW = "correct-horse-battery"


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setattr(settings, "app_password", PW)
    monkeypatch.setattr(settings, "secret_key", "s" * 32)
    monkeypatch.setattr(settings, "cron_token", "cron-secret-token")
    auth.reset_limits()
    yield
    auth.reset_limits()


def test_api_requires_login(client, locked):
    client.cookies.clear()
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/profile").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/me").json() == {"auth_required": True, "authenticated": False}


def test_login_flow_and_logout(client, locked):
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    r = client.post("/api/auth/login", json={"password": PW})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/jobs").status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is True
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/jobs").status_code == 401


def test_login_needs_client_header(client, locked):
    from fastapi.testclient import TestClient

    from app.main import app

    bare = TestClient(app)
    assert bare.post("/api/auth/login", json={"password": PW}).status_code == 403


def test_rate_limit(client, locked):
    client.cookies.clear()
    for _ in range(auth.MAX_PER_IP):
        assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"password": PW})  # حتى الصحيحة تُرفض أثناء الحظر
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_tokens(locked):
    t = auth.make_token()
    assert auth.valid_token(t)
    assert not auth.valid_token(t[:-1] + ("0" if t[-1] != "0" else "1"))  # توقيع معدّل
    assert not auth.valid_token("v1.9999999999.deadbeef")
    assert not auth.valid_token(t, now=time.time() + settings.session_hours * 3600 + 10)  # منتهية
    settings.app_password = PW + "-changed"  # تغيير كلمة المرور يبطل الجلسات القائمة
    assert not auth.valid_token(t)


def test_forged_cookie_rejected(client, locked):
    client.cookies.clear()
    client.cookies.set(auth.COOKIE, "v1.9999999999.abc")
    assert client.get("/api/jobs").status_code == 401
    client.cookies.clear()


def test_cron_endpoint(client, locked):
    from fastapi.testclient import TestClient

    from app.main import app

    bare = TestClient(app)  # بلا كوكي وبلا ترويسة الواجهة، كما تفعل GitHub Actions
    assert bare.post("/api/cron/collect").status_code == 401
    assert bare.post("/api/cron/collect", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = bare.post("/api/cron/collect", headers={"Authorization": "Bearer cron-secret-token"})
    assert r.status_code == 202


def test_cron_disabled_without_token(client, monkeypatch):
    monkeypatch.setattr(settings, "cron_token", "")
    assert client.post("/api/cron/collect", headers={"Authorization": "Bearer "}).status_code == 401


def test_security_headers(client):
    h = client.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["cache-control"] == "no-store"


def test_postgres_url_normalized(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@ep-x.neon.tech/db?sslmode=require")
    import importlib

    import app.config as cfg

    s = importlib.reload(cfg).Settings()
    assert s.database_url == "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"
    monkeypatch.setenv("DATABASE_URL", "")
    importlib.reload(cfg)


def test_production_requires_secrets(monkeypatch):
    monkeypatch.setattr(Settings, "environment", "production")
    monkeypatch.setattr(Settings, "app_password", "")
    with pytest.raises(RuntimeError):
        Settings()
    monkeypatch.setattr(Settings, "app_password", "short")
    monkeypatch.setattr(Settings, "secret_key", "k")
    with pytest.raises(RuntimeError):
        Settings()


def test_cv_stored_in_db(client):
    pdf = b"%PDF-1.4\n%test\n"
    r = client.post("/api/profile/cv", files={"file": ("me.pdf", pdf, "application/pdf")})
    assert r.status_code == 200
    assert client.get("/api/status").json()["cv_uploaded"] is True
    from app.db import SessionLocal
    from app.models import Profile

    with SessionLocal() as s:
        assert s.get(Profile, 1).cv_data == pdf
    assert not (settings.data_dir / "cv.pdf").exists()
