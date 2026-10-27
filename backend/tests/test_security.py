"""اختبارات انحدار للثغرات التي اكتُشفت في المراجعة التقنية."""
import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.collectors import CollectorError
from app.collectors import http as h
from app.main import app


def _draft(client, email="hr@sec.sa", title="Sec Dev"):
    j = client.post("/api/jobs", json={"title": f"{title} {time.time_ns()}", "description": "Python",
                                       "contact_email": email}).json()
    a = client.post(f"/api/jobs/{j['id']}/application", json={}).json()
    client.patch(f"/api/applications/{a['id']}", json={"attach_cv": False})
    return j, a


def test_csrf_request_without_client_header_is_rejected(client):
    _, a = _draft(client)
    anon = TestClient(app)  # بلا الترويسة: مثل نموذج POST من موقع آخر
    with patch("app.mailer.send") as send:
        r = anon.post(f"/api/applications/{a['id']}/send", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and not send.called
    assert anon.get("/api/jobs").status_code == 200  # القراءة متاحة، والمتصفح يمنع المواقع الأخرى من قراءتها


def test_cors_preflight_only_for_frontend(client):
    pre = lambda origin: client.options("/api/jobs", headers={  # noqa: E731
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-forsa-client,content-type"})
    assert pre("http://localhost:3000").headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in pre("https://evil.example").headers


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,<script>", "ftp://x"])
def test_dangerous_urls_rejected(client, url):
    r = client.post("/api/jobs", json={"title": "Url test", "url": url})
    assert r.status_code == 422


def test_scraped_dangerous_url_is_dropped(client):
    from app.collectors.base import RawJob
    with patch.dict("app.services.COLLECTORS", {"rss": lambda cfg: [
            RawJob(title="Scraped js link", description="x", url="javascript:alert(1)")]}):
        sid = client.post("/api/sources", json={"name": "s", "kind": "rss", "config": {"url": "https://a.sa"}}).json()["id"]
        client.post(f"/api/sources/{sid}/run")
    items = client.get("/api/jobs", params={"q": "Scraped js link"}).json()["items"]
    assert items and items[0]["url"] is None


def test_header_injection_blocked(client):
    _, a = _draft(client)
    r = client.patch(f"/api/applications/{a['id']}", json={"subject": "Hi\r\nBcc: spy@evil.example"})
    assert r.status_code == 422
    r = client.patch(f"/api/applications/{a['id']}", json={"to_email": "a@b.sa\nBcc: x@y.sa"})
    assert r.status_code == 422


def test_double_click_sends_one_email(client):
    _, a = _draft(client)
    sent = []
    codes = []

    def slow(msg, **_):
        time.sleep(0.3)
        sent.append(msg)

    with patch("app.mailer.send", side_effect=slow):
        ts = [threading.Thread(target=lambda: codes.append(client.post(f"/api/applications/{a['id']}/send").status_code))
              for _ in range(3)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    assert len(sent) == 1
    assert sorted(codes) == [200, 400, 400]


def test_unexpected_send_error_marks_failed_and_allows_retry(client):
    _, a = _draft(client)
    with patch("app.mailer.send", side_effect=RuntimeError("boom")):
        r = client.post(f"/api/applications/{a['id']}/send")
    assert r.status_code == 400
    apps = {x["id"]: x for x in client.get("/api/applications").json()}
    assert apps[a["id"]]["status"] == "failed"
    with patch("app.mailer.send"):
        assert client.post(f"/api/applications/{a['id']}/send").status_code == 200


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/", "http://169.254.169.254/latest", "http://10.0.0.5/x",
                                 "http://localhost/", "file:///etc/passwd"])
def test_ssrf_internal_addresses_blocked(url):
    with pytest.raises(CollectorError):
        h.fetch(url)


def test_profile_validation(client):
    assert client.put("/api/profile", json={"years_experience": -5}).status_code == 422
    assert client.put("/api/profile", json={"email": "not-an-email"}).status_code == 422


def test_datetimes_are_utc_aware(client):
    j = client.post("/api/jobs", json={"title": "Tz check job"}).json()
    listed = client.get(f"/api/jobs/{j['id']}").json()
    assert listed["created_at"].endswith(("Z", "+00:00"))
