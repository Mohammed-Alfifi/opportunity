"""ناقل Gmail Apps Script: نتحقق من شكل الطلب، التحويل 302، ومفتاح منع التكرار، دون الاتصال بجوجل."""
import base64
import json

import httpx
import pytest

from app import mailer
from app.config import settings


@pytest.fixture
def gas(monkeypatch):
    monkeypatch.setattr(settings, "mail_transport", "gas")
    monkeypatch.setattr(settings, "gas_url", "https://script.google.com/macros/s/ABC/exec")
    monkeypatch.setattr(settings, "gas_token", "t" * 32)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "script.google.com":
            seen.append(json.loads(request.content))
            return httpx.Response(302, headers={"location": "https://script.googleusercontent.com/echo?x=1"})
        assert request.method == "GET"
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(httpx, "post", lambda url, json, **k: client.post(url, json=json))
    return seen


def test_gas_send(gas):
    msg = mailer.build_message("hr@example.com", "طلب وظيفة", "مرحباً", "سارة", "me@example.org", b"%PDF-1", "cv.pdf")
    mailer.send(msg, key="forsa-1-abc")
    p = gas[0]
    assert p["to"] == "hr@example.com" and p["subject"] == "طلب وظيفة" and p["name"] == "سارة"
    assert p["body"].strip() == "مرحباً" and p["key"] == "forsa-1-abc" and p["token"] == "t" * 32
    assert base64.b64decode(p["attachments"][0]["data"]) == b"%PDF-1"
    assert p["attachments"][0]["name"] == "cv.pdf"


def test_gas_rejects_foreign_url(gas, monkeypatch):
    monkeypatch.setattr(settings, "gas_url", "https://evil.example.com/exec")
    msg = mailer.build_message("hr@example.com", "s", "b", "", None, None, None)
    with pytest.raises(mailer.MailError):
        mailer.send(msg)


def test_gas_error_surfaces(monkeypatch):
    monkeypatch.setattr(settings, "mail_transport", "gas")
    monkeypatch.setattr(settings, "gas_url", "https://script.google.com/macros/s/ABC/exec")
    monkeypatch.setattr(settings, "gas_token", "t" * 32)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": False, "error": "رمز غير صالح"})))
    monkeypatch.setattr(httpx, "post", lambda url, json, **k: client.post(url, json=json))
    msg = mailer.build_message("hr@example.com", "s", "b", "", None, None, None)
    with pytest.raises(mailer.MailError, match="رمز غير صالح"):
        mailer.send(msg)


def test_status_reports_transport(client, gas):
    s = client.get("/api/status").json()["smtp"]
    assert s["configured"] is True and s["transport"] == "gas"
