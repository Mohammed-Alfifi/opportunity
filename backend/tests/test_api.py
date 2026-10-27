from unittest.mock import patch

from app.analysis import heuristic
from app.collectors.base import RawJob

PROFILE = {
    "full_name": "محمد", "email": "me@example.org", "headline": "Software Engineer | AI & Automation",
    "summary": "أبني أنظمة ذكاء اصطناعي وتطبيقات ويب.", "skills": ["Python", "FastAPI", "Docker", "Computer Vision"],
    "target_titles": ["AI Engineer", "مطور Python"], "locations": ["الرياض", "Remote"],
    "years_experience": 3, "links": ["https://github.com/example"],
}


def test_heuristic_scores_relevant_higher():
    good = {"title": "AI Engineer", "description": "Python, FastAPI, Docker, computer vision. Riyadh. 2 years",
            "location": "Riyadh"}
    bad = {"title": "محاسب", "description": "خبرة 10 سنوات في SAP و Excel", "location": "جدة"}
    g, b = heuristic.analyze(good, PROFILE), heuristic.analyze(bad, PROFILE)
    assert g["score"] > 70 > b["score"]
    assert "Python" in g["matched_skills"]
    assert b["required_years"] == 10


def test_full_flow(client):
    assert client.put("/api/profile", json=PROFILE).status_code == 200

    r = client.post("/api/sources", json={"name": "قناة", "kind": "telegram",
                                          "config": {"channel": "jobs_ksa", "include_keywords": ["مطور", "engineer"]}})
    assert r.status_code == 201
    sid = r.json()["id"]

    raws = [RawJob(title="مطلوب مطور Python", description="FastAPI و Docker في الرياض hr@co.sa"),
            RawJob(title="مطلوب سائق", description="رخصة قيادة"),
            RawJob(title="مطلوب مطور Python", description="FastAPI و Docker في الرياض hr@co.sa")]
    with patch.dict("app.services.COLLECTORS", {"telegram": lambda cfg: raws}):
        r = client.post(f"/api/sources/{sid}/run")
    assert r.status_code == 200 and r.json()["last_new_count"] == 1 and r.json()["job_count"] == 1

    jobs = client.get("/api/jobs", params={"sort": "score"}).json()
    assert jobs["total"] == 1
    job = jobs["items"][0]
    assert job["contact_email"] == "hr@co.sa" and job["lang"] == "ar" and job["score"] >= 50

    d = client.get(f"/api/jobs/{job['id']}").json()
    assert d["analysis"]["engine"] == "heuristic"

    app = client.post(f"/api/jobs/{job['id']}/application", json={}).json()
    assert app["status"] == "draft" and "مطور Python" in app["subject"] and app["to_email"] == "hr@co.sa"

    r = client.patch(f"/api/applications/{app['id']}", json={"attach_cv": False, "body": app["body"] + "\nشكراً"})
    assert r.status_code == 200

    sent = []
    with patch("app.mailer.send", side_effect=lambda m, **k: sent.append(m)):
        r = client.post(f"/api/applications/{app['id']}/send")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent" and sent[0]["To"] == "hr@co.sa"
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "applied"
    assert client.post(f"/api/applications/{app['id']}/send").status_code == 400

    stats = client.get("/api/jobs/stats").json()
    assert stats["sent"] == 1


def test_send_requires_cv_when_attached(client):
    j = client.post("/api/jobs", json={"title": "Python Developer", "description": "Python", "contact_email": "a@b.sa"}).json()
    app = client.post(f"/api/jobs/{j['id']}/application", json={"lang": "en"}).json()
    assert app["subject"].startswith("Application:")
    r = client.post(f"/api/applications/{app['id']}/send")
    assert r.status_code == 400 and "PDF" in r.json()["detail"]
    assert client.post("/api/jobs", json={"title": "Python Developer", "description": "Python"}).status_code == 409


def test_source_error_is_recorded(client):
    sid = client.post("/api/sources", json={"name": "rss", "kind": "rss", "config": {}}).json()["id"]
    r = client.post(f"/api/sources/{sid}/run").json()
    assert "url" in r["last_error"]


def test_cv_upload_rejects_non_pdf(client):
    r = client.post("/api/profile/cv", files={"file": ("cv.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_arabic_post_matches_english_profile():
    job = {"title": "مطلوب مهندس رؤية حاسوبية - الرياض", "description": "خبرة سنتين في Python و OpenCV و Docker"}
    a = heuristic.analyze(job, PROFILE)
    assert "Computer Vision" in a["matched_skills"]
    assert a["score"] >= 70, a


def test_scheduled_collect_runs_enabled_sources(client):
    from app import main
    calls = []
    with patch.dict("app.services.COLLECTORS", {"rss": lambda cfg: calls.append(cfg) or []}):
        client.post("/api/sources", json={"name": "on", "kind": "rss", "config": {"url": "https://a.sa/f"}})
        off = client.post("/api/sources", json={"name": "off", "kind": "rss", "config": {"url": "https://b.sa/f"},
                                                "enabled": False})
        assert off.status_code == 201
        main.scheduled_collect()
    urls = [c.get("url") for c in calls]
    assert "https://a.sa/f" in urls and "https://b.sa/f" not in urls
