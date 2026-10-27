"""اختبار تكامل كامل: يشغّل الخلفية فعلياً على منفذ ويجمع من خوادم محاكاة ويرسل إلى خادم بريد حقيقي.

التشغيل:  python tests/integration/run_integration.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from mock_world import MockSMTP, MockWeb  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]
API_PORT, WEB_PORT, SMTP_PORT = 8100, 8765, 2525
API = f"http://127.0.0.1:{API_PORT}"
H = {"x-forsa-client": "web"}

results: list[dict] = []


def check(name: str, fn):
    t0 = time.perf_counter()
    try:
        detail = fn()
        ok = True
    except AssertionError as e:
        ok, detail = False, f"فشل: {e}"
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"خطأ: {type(e).__name__}: {e}"
    ms = round((time.perf_counter() - t0) * 1000)
    results.append({"name": name, "ok": ok, "ms": ms, "detail": detail})
    print(f"{'✔' if ok else '✘'} {name} ({ms}ms) {detail or ''}")


def minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def main() -> int:
    data_dir = tempfile.mkdtemp(prefix="forsa-it-")
    with MockWeb(WEB_PORT) as web, MockSMTP(SMTP_PORT) as smtp:
        env = {**os.environ,
               "DATA_DIR": data_dir, "SCHEDULER_ENABLED": "false", "ALLOW_PRIVATE_NETWORK": "true",
               "TELEGRAM_BASE_URL": f"{web.url}/s", "HTTP_TIMEOUT": "2",
               "LLM_PROVIDER": "openai", "LLM_MODEL": "mock", "LLM_API_KEY": "k", "LLM_BASE_URL": f"{web.url}/v1",
               "SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(SMTP_PORT), "SMTP_SECURITY": "none",
               "SMTP_USER": "me@forsa.test", "SMTP_PASSWORD": "", "CORS_ORIGINS": "http://localhost:3100"}
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(API_PORT)],
                                cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        c = httpx.Client(base_url=API, headers=H, timeout=30)
        try:
            for _ in range(50):
                try:
                    if c.get("/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.2)
            ids: dict = {}

            def t_health():
                assert c.get("/api/health").json() == {"ok": True}

            def t_csrf():
                r = httpx.post(f"{API}/api/sources/run-all")
                assert r.status_code == 403, r.status_code
                return "طلب بلا ترويسة الواجهة رُفض بـ 403"

            def t_profile():
                r = c.put("/api/profile", json={
                    "full_name": "محمد", "email": "me@forsa.test", "phone": "0500000000",
                    "headline": "Software Engineer | AI & Automation", "summary": "أبني أنظمة تحليل فيديو وتطبيقات ويب.",
                    "skills": ["Python", "FastAPI", "Docker", "Computer Vision", "React", "PostgreSQL", "YOLO"],
                    "target_titles": ["AI Engineer", "Computer Vision Engineer", "مهندس ذكاء اصطناعي"],
                    "locations": ["الرياض", "Riyadh", "Remote"], "years_experience": 3, "links": ["https://github.com/x"]})
                assert r.status_code == 200, r.text

            def t_cv():
                r = c.post("/api/profile/cv", files={"file": ("Mohammed-CV.pdf", minimal_pdf("Python OpenCV engineer"), "application/pdf")})
                assert r.status_code == 200, r.text
                assert "OpenCV" in r.json()["cv_text"], "لم يُستخرج نص السيرة"
                return "رُفعت السيرة واستُخرج نصها"

            def t_sources():
                specs = [
                    ("tg", {"name": "قناة تقنية", "kind": "telegram", "config": {"channel": "@ksa_tech", "exclude_keywords": ["سائق"]}}),
                    ("rss", {"name": "موقع توظيف", "kind": "rss", "config": {"url": f"{web.url}/feed.xml"}}),
                    ("gov", {"name": "بوابة جهة حكومية", "kind": "webpage", "config": {"url": f"{web.url}/careers"}}),
                    ("empty", {"name": "صفحة بلا بيانات", "kind": "webpage", "config": {"url": f"{web.url}/empty"}}),
                    ("big", {"name": "صفحة ضخمة", "kind": "webpage", "config": {"url": f"{web.url}/big"}}),
                    ("slow", {"name": "خادم بطيء", "kind": "rss", "config": {"url": f"{web.url}/slow"}}),
                    ("dead", {"name": "رابط معطل", "kind": "rss", "config": {"url": f"{web.url}/missing"}}),
                ]
                for key, body in specs:
                    r = c.post("/api/sources", json=body)
                    assert r.status_code == 201, r.text
                    ids[key] = r.json()["id"]
                return f"{len(specs)} مصادر"

            def t_collect():
                r = c.post("/api/sources/run-all").json()
                per = {int(k): v for k, v in r["per_source"].items()}
                got = {k: per[v] for k, v in ids.items()}
                assert got["tg"] == 2, f"تيليجرام: {got['tg']} (المتوقع 2 بعد استبعاد السائق)"
                assert got["rss"] == 1, f"RSS: {got['rss']} (المتوقع 1؛ الأخرى مكررة من تيليجرام بنفس الرابط)"
                assert got["gov"] == 2, f"الجهة: {got['gov']}"
                return f"{r['new_jobs']} وظيفة جديدة: {got}"

            def t_errors():
                srcs = {s["id"]: s for s in c.get("/api/sources").json()}
                errs = {k: srcs[ids[k]]["last_error"] for k in ("empty", "big", "slow", "dead")}
                assert all(errs.values()), errs
                assert "ميجابايت" in errs["big"] and "404" in errs["dead"]
                assert srcs[ids["tg"]]["last_error"] is None
                return "الأخطاء الأربعة مسجلة برسائل واضحة ولم توقف بقية المصادر"

            def t_idempotent():
                r = c.post("/api/sources/run-all").json()
                assert r["new_jobs"] == 0, r
                return "إعادة الجمع لم تُضف أي مكرر"

            def t_ranking():
                items = c.get("/api/jobs", params={"sort": "score"}).json()["items"]
                titles = [i["title"] for i in items]
                ids["top"] = next(i["id"] for i in items if i["contact_email"])  # أعلى فرصة فيها بريد تقديم
                assert "SAP" in titles[-1] or "SAP" in titles[-2], titles
                assert items[0]["score"] >= 70, items[0]
                return " > ".join(f"{i['title'][:22]}({i['score']})" for i in items)

            def t_extraction():
                items = c.get("/api/jobs").json()["items"]
                by = {i["title"]: i for i in items}
                tg = next(i for t, i in by.items() if "رؤية حاسوبية" in t)
                assert tg["contact_email"] == "talent@vision.sa", tg
                assert tg["url"].startswith("https://vision.sa/jobs/cv-01"), tg["url"]
                gov = next(i for t, i in by.items() if "ذكاء اصطناعي" in t)
                assert gov["company"] == "هيئة تقنية" and "الرياض" in gov["location"], gov
                ml = next(i for t, i in by.items() if "Machine Learning" in t)
                assert ml["lang"] == "en" and ml["contact_email"] == "careers@ml.sa"
                assert ml["created_at"].endswith(("Z", "+00:00"))
                return "البريد والرابط والجهة والمدينة واللغة استُخرجت صحيحة"

            def t_import():
                r = c.post("/api/jobs/import-url", json={"url": f"{web.url}/job/single"})
                assert r.status_code == 201, r.text
                j = r.json()
                assert j["title"].startswith("Senior Backend") and j["contact_email"] == "hiring@payco.sa", j
                assert "menu" not in j["description"]
                r2 = c.post("/api/jobs/import-url", json={"url": f"{web.url}/job/single"})
                assert r2.status_code == 409
                return "استيراد رابط واحد + رفض التكرار"

            def t_llm_analysis():
                r = c.post(f"/api/jobs/{ids['top']}/analyze").json()
                a = r["analysis"]
                assert a["engine"] == "llm" and r["score"] == 88 and a["tips"], a
                assert "heuristic_score" in a
                return f"تحليل النموذج: {r['score']}، والتقييم السريع كان {a['heuristic_score']}"

            def t_letter():
                r = c.post(f"/api/jobs/{ids['top']}/application", json={"lang": "ar", "instructions": "ركّز على الكاميرات"})
                assert r.status_code == 200, r.text
                app = r.json()
                ids["app"] = app["id"]
                assert app["subject"] == "تقديم: مهندس رؤية حاسوبية" and app["status"] == "draft"
                assert "ركّز على الكاميرات" in web.llm_calls[-1]
                return "الرسالة من النموذج، والتوجيه الإضافي وصل له"

            def t_send():
                r = c.post(f"/api/applications/{ids['app']}/send")
                assert r.status_code == 200, r.text
                assert len(smtp.messages) == 1, len(smtp.messages)
                m = smtp.messages[0]["msg"]
                from email.header import decode_header, make_header
                subj = str(make_header(decode_header(m["Subject"])))
                atts = [p.get_filename() for p in m.walk() if p.get_filename()]
                assert subj == "تقديم: مهندس رؤية حاسوبية", subj
                expected = c.get(f"/api/jobs/{ids['top']}").json()["contact_email"]
                assert smtp.messages[0]["rcpt"] == [expected], (smtp.messages[0]["rcpt"], expected)
                assert m["Reply-To"] is None and "me@forsa.test" in m["From"], (m["From"], m["Reply-To"])
                assert atts == ["Mohammed-CV.pdf"], atts
                return f"وصلت رسالة حقيقية للخادم: إلى {smtp.messages[0]['rcpt'][0]}، مرفق {atts[0]}"

            def t_after_send():
                j = c.get(f"/api/jobs/{ids['top']}").json()
                assert j["status"] == "applied"
                assert c.post(f"/api/applications/{ids['app']}/send").status_code == 400
                assert c.patch(f"/api/applications/{ids['app']}", json={"body": "x"}).status_code == 409
                assert c.get("/api/jobs/stats").json()["sent"] == 1
                return "الحالة «تم التقديم»، وإعادة الإرسال والتعديل مرفوضان"

            def t_template_fallback():
                j = c.post("/api/jobs", json={"title": "Data Engineer", "description": "Spark ETL", "contact_email": "d@e.sa"}).json()
                r = c.post(f"/api/jobs/{j['id']}/application", json={"use_llm": False, "lang": "en"}).json()
                assert r["subject"].startswith("Application:") and "أبني" not in r["body"]
                return "القالب الجاهز يعمل بدون نموذج، ولا يخلط النبذة العربية في رسالة إنجليزية"

            def t_delete_source():
                before = c.get("/api/jobs").json()["total"]
                assert c.delete(f"/api/sources/{ids['gov']}").status_code == 204
                after = c.get("/api/jobs").json()
                assert after["total"] == before
                return "حذف المصدر أبقى وظائفه"

            def t_ignore_filter():
                j = c.get("/api/jobs", params={"q": "SAP"}).json()["items"][0]
                c.patch(f"/api/jobs/{j['id']}", json={"status": "ignored"})
                assert not c.get("/api/jobs", params={"q": "SAP"}).json()["items"]
                assert c.get("/api/jobs", params={"status": "ignored"}).json()["total"] == 1

            for name, fn in [
                ("تشغيل الخادم والصحة", t_health), ("حماية CSRF على الخادم الحي", t_csrf),
                ("حفظ الملف الشخصي", t_profile), ("رفع السيرة واستخراج النص", t_cv),
                ("إضافة 7 مصادر (منها 4 معطلة عمداً)", t_sources), ("الجمع من كل المصادر", t_collect),
                ("تسجيل أخطاء المصادر المعطلة", t_errors), ("إعادة الجمع بلا تكرار", t_idempotent),
                ("ترتيب الفرص بالتوافق", t_ranking), ("استخراج بيانات الإعلانات", t_extraction),
                ("استيراد وظيفة من رابط", t_import), ("تحليل عميق بنموذج اللغة", t_llm_analysis),
                ("كتابة رسالة التقديم بالنموذج", t_letter), ("الإرسال الفعلي عبر SMTP", t_send),
                ("الحالة بعد الإرسال", t_after_send), ("القالب الاحتياطي بالإنجليزية", t_template_fallback),
                ("حذف مصدر", t_delete_source), ("التجاهل والفرز", t_ignore_filter),
            ]:
                check(name, fn)
        finally:
            c.close()
            proc.terminate()
            err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            proc.wait(5)
            crashes = [ln for ln in err.splitlines() if "Traceback" in ln or "Exception in ASGI" in ln]
            results.append({"name": "سجل الخادم بلا أعطال", "ok": not crashes, "ms": 0,
                            "detail": f"{len(crashes)} عطل" if crashes else "لا استثناءات غير معالجة"})
    out = Path(os.environ.get("RESULTS_FILE", Path(data_dir) / "integration.json"))
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    passed = sum(r["ok"] for r in results)
    print(f"\n{passed}/{len(results)} نجح — النتائج في {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
