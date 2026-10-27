"""اختبار شامل عبر المتصفح: رحلة المستخدم من الدخول وإعداد الملف حتى وصول التقديم لبريد جهة التوظيف.

يشغّل نفس شكل النشر: واجهة ثابتة تخدمها الخلفية من نفس الأصل، بكلمة مرور.

المتطلبات: pip install playwright && playwright install chromium
التشغيل:   python e2e/run_e2e.py   (يبني الواجهة ويشغّل كل شيء بنفسه)
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
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "tests" / "integration"))
from mock_world import MockSMTP, MockWeb  # noqa: E402
from run_integration import minimal_pdf  # noqa: E402

API_PORT, WEB_PORT, SMTP_PORT = 8100, 8766, 2526
PASSWORD = "e2e-password-123"
SHOTS = Path(os.environ.get("SHOTS_DIR", tempfile.mkdtemp(prefix="forsa-e2e-")))
SHOTS.mkdir(parents=True, exist_ok=True)
results: list[dict] = []


def step(name, fn, page=None):
    t0 = time.perf_counter()
    try:
        detail = fn()
        ok = True
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: " + " | ".join(l.strip() for l in str(e).splitlines() if l.strip())[:400]
    ms = round((time.perf_counter() - t0) * 1000)
    shot = None
    if page is not None:
        shot = SHOTS / f"{len(results) + 1:02d}.png"
        page.screenshot(path=str(shot), full_page=True)
    results.append({"name": name, "ok": ok, "ms": ms, "detail": detail, "shot": str(shot) if shot else None})
    print(f"{'✔' if ok else '✘'} {name} ({ms}ms) {detail or ''}")


def main() -> int:
    py = sys.executable
    backend_py = ROOT / "backend" / ".venv" / "bin" / "python"
    data_dir = tempfile.mkdtemp(prefix="forsa-e2e-data-")
    cv = Path(data_dir) / "Mohammed-CV.pdf"
    cv.write_bytes(minimal_pdf("Python OpenCV engineer"))

    if not os.environ.get("SKIP_BUILD"):
        subprocess.run(["npx", "next", "build"], cwd=ROOT / "frontend", check=True, capture_output=True,
                       env={**os.environ, "NEXT_PUBLIC_API_URL": ""})

    with MockWeb(WEB_PORT) as web, MockSMTP(SMTP_PORT) as smtp:
        env = {**os.environ, "DATA_DIR": data_dir, "SCHEDULER_ENABLED": "false", "ALLOW_PRIVATE_NETWORK": "true",
               "TELEGRAM_BASE_URL": f"{web.url}/s", "LLM_PROVIDER": "none",
               "SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(SMTP_PORT), "SMTP_SECURITY": "none",
               "SMTP_USER": "me@forsa.test", "SMTP_PASSWORD": "", "APP_PASSWORD": PASSWORD,
               "SECRET_KEY": "e2e-secret", "STATIC_DIR": str(ROOT / "frontend" / "out")}
        api = subprocess.Popen([str(backend_py if backend_py.exists() else py), "-m", "uvicorn", "app.main:app",
                                "--port", str(API_PORT)], cwd=ROOT / "backend", env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for url in (f"http://127.0.0.1:{API_PORT}/api/health", f"http://127.0.0.1:{API_PORT}/"):
                for _ in range(80):
                    try:
                        if httpx.get(url).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.25)
            run(f"http://127.0.0.1:{API_PORT}", cv, smtp)
        finally:
            api.terminate()
    (SHOTS / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    passed = sum(r["ok"] for r in results)
    print(f"\n{passed}/{len(results)} نجح — اللقطات في {SHOTS}")
    return 0 if passed == len(results) else 1


def run(base: str, cv: Path, smtp) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 860}, locale="ar-SA")
        page = ctx.new_page()
        console_errors, failed = [], []
        page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
        page.on("requestfailed", lambda r: "fonts.g" not in r.url and failed.append(r.url))
        page.on("dialog", lambda d: d.accept())

        def login():
            page.goto(base + "/")
            # بلا جلسة: الـ API مغلق والواجهة تعرض الدخول فقط
            assert httpx.get(base + "/api/jobs").status_code == 401
            page.get_by_label("كلمة المرور").fill("wrong-password")
            page.get_by_role("button", name="دخول").click()
            expect(page.locator(".notice.error[role=alert]")).to_contain_text("كلمة المرور غير صحيحة")
            page.get_by_label("كلمة المرور").fill(PASSWORD)
            page.get_by_role("button", name="دخول").click()
            expect(page.get_by_role("link", name="الفرص")).to_be_visible()
            cookie = next(c for c in ctx.cookies() if c["name"] == "forsa_session")
            assert cookie["httpOnly"] and cookie["sameSite"] == "Lax", cookie
            return "كلمة خاطئة تُرفض، والصحيحة تفتح المنصة بكوكي HttpOnly"

        def logout():
            page.goto(base + "/")
            page.get_by_role("button", name="تسجيل الخروج").click()
            expect(page.get_by_label("كلمة المرور")).to_be_visible()
            page.reload()
            expect(page.get_by_label("كلمة المرور")).to_be_visible()
            page.get_by_label("كلمة المرور").fill(PASSWORD)
            page.get_by_role("button", name="دخول").click()
            expect(page.get_by_role("link", name="الفرص")).to_be_visible()
            return "الخروج يعيد صفحة الدخول ويبقى بعد التحديث"

        def empty_state():
            page.goto(base + "/")
            expect(page.get_by_role("heading", name="لا توجد فرص بعد")).to_be_visible()
            return "شاشة فارغة توجّه لإضافة المصادر"

        def profile():
            page.goto(base + "/profile")
            page.get_by_label("الاسم").fill("محمد")
            page.get_by_label("المسمى المهني").fill("Software Engineer | AI & Automation")
            page.get_by_label("البريد").fill("me@forsa.test")
            page.get_by_label("المهارات (افصل بفاصلة)").fill("Python، FastAPI، Docker، Computer Vision، React، PostgreSQL")
            page.get_by_label("الوظائف التي تستهدفها").fill("AI Engineer، Computer Vision Engineer، مطور Full-Stack")
            page.get_by_label("المدن المفضلة").fill("الرياض، Remote")
            page.get_by_label("سنوات الخبرة").fill("3")
            page.get_by_role("button", name="حفظ الملف").click()
            expect(page.get_by_role("status")).to_contain_text("حُفظ ملفك")
            page.locator("input[type=file]").set_input_files(str(cv))
            expect(page.get_by_role("status")).to_contain_text("رُفعت السيرة")
            expect(page.get_by_text("الملف الحالي: Mohammed-CV.pdf")).to_be_visible()
            return "حفظ الملف + رفع السيرة"

        def bad_email():
            page.get_by_label("البريد").fill("not-an-email")
            page.get_by_role("button", name="حفظ الملف").click()
            valid = page.get_by_label("البريد").evaluate("el => el.checkValidity()")
            assert valid is False, "المتصفح قبل بريداً غير صالح"
            # الطبقة الثانية: الخادم يرفض حتى لو تجاوز أحد تحقق المتصفح
            r = page.request.put(base + "/api/profile", data=json.dumps({"email": "not-an-email"}),
                                 headers={"x-forsa-client": "web", "content-type": "application/json"})
            assert r.status == 422 and "بريد إلكتروني غير صالح" in r.text(), r.text()
            page.get_by_label("البريد").fill("me@forsa.test")
            page.get_by_role("button", name="حفظ الملف").click()
            expect(page.get_by_role("status")).to_contain_text("حُفظ ملفك")
            return "المتصفح يمنع الإرسال، والخادم يرفض برسالة عربية"

        def add_source():
            page.goto(base + "/sources")
            page.get_by_role("button", name="إضافة مصدر").first.click()
            dlg = page.locator("dialog[open]")
            dlg.get_by_label("الاسم").fill("قناة تقنية")
            dlg.get_by_label("القناة").fill("@ksa_tech")
            dlg.get_by_label("استبعد ما يحتوي (اختياري)").fill("سائق")
            dlg.get_by_role("button", name="أضف المصدر").click()
            expect(page.get_by_role("cell", name="قناة تقنية")).to_be_visible()
            page.get_by_role("button", name="اجمع", exact=True).click()
            expect(page.get_by_text("2 جديدة")).to_be_visible(timeout=15000)
            return "أُضيف المصدر وجمع وظيفتين (استُبعد إعلان السائق)"

        def collect_and_rank():
            page.goto(base + "/")
            page.get_by_role("button", name="اجمع الآن").click()
            expect(page.get_by_role("status")).to_contain_text("لا توجد فرص جديدة")
            rows = page.locator("article.job")
            expect(rows).to_have_count(2)
            scores = [int(t) for t in page.locator("article.job .ring .val").all_inner_texts()]
            assert scores == sorted(scores, reverse=True), scores
            return f"الترتيب بالتوافق: {scores}"

        def search_filter():
            page.get_by_label("بحث").fill("Full-Stack")
            expect(page.locator("article.job")).to_have_count(1)
            page.get_by_label("بحث").fill("")
            expect(page.locator("article.job")).to_have_count(2)
            return "البحث يفلتر النتائج"

        def open_and_draft():
            page.locator("article.job h3 a").first.click()
            expect(page.get_by_role("heading", name="رسالة التقديم")).to_be_visible()
            page.get_by_role("button", name="جهّز الرسالة").click()
            expect(page.get_by_label("الموضوع")).not_to_have_value("")
            body = page.get_by_label("النص").input_value()
            assert "محمد" in body and "السلام عليكم" in body, body[:80]
            return "رسالة عربية فيها الاسم والتحية"

        def send():
            to = page.get_by_label("إلى")
            if not to.input_value():
                to.fill("talent@vision.sa")
            page.get_by_label("النص").fill(page.get_by_label("النص").input_value() + "\nملاحظة من اختبار E2E")
            page.get_by_role("button", name="أرسل التقديم").click()
            expect(page.get_by_role("status")).to_contain_text("أُرسل التقديم")
            for _ in range(20):
                if smtp.messages:
                    break
                time.sleep(0.1)
            assert len(smtp.messages) == 1, len(smtp.messages)
            msg = smtp.messages[0]["msg"]
            body = msg.get_body(preferencelist=("plain",)).get_content()
            assert "ملاحظة من اختبار E2E" in body, "التعديل اليدوي لم يصل"
            atts = [p.get_filename() for p in msg.walk() if p.get_filename()]
            assert atts == ["Mohammed-CV.pdf"], atts
            return f"وصلت إلى {smtp.messages[0]['rcpt'][0]} بالتعديل اليدوي والسيرة مرفقة"

        def applications():
            page.goto(base + "/applications")
            expect(page.get_by_text("مرسل", exact=True)).to_be_visible()
            return "التقديم ظاهر بحالة مرسل"

        def mobile():
            m = ctx.new_page()
            m.set_viewport_size({"width": 390, "height": 844})
            for path in ("/", "/sources", "/profile", "/jobs/?id=1"):
                m.goto(base + path)
                m.wait_for_load_state("networkidle")
                w = m.evaluate("document.documentElement.scrollWidth")
                assert w <= 390, f"{path}: عرض الصفحة {w}px"
            m.screenshot(path=str(SHOTS / "mobile-job.png"), full_page=True)
            m.close()
            return "4 صفحات بلا تمرير أفقي على 390px"

        def keyboard():
            page.goto(base + "/")
            expect(page.get_by_role("link", name="الفرص")).to_be_visible()
            page.keyboard.press("Tab")
            tag = page.evaluate("document.activeElement.tagName")
            assert tag != "BODY", "لا يوجد تركيز"
            focused = page.evaluate("document.activeElement.textContent")
            return f"أول عنصر بالتركيز: {focused.strip()[:20]}"

        def dark():
            dc = browser.new_context(viewport={"width": 1280, "height": 860}, color_scheme="dark")
            dc.add_cookies([c for c in ctx.cookies() if c["name"] == "forsa_session"])
            d = dc.new_page()
            d.goto(base + "/jobs/?id=1")
            d.wait_for_load_state("networkidle")
            bg = d.evaluate("getComputedStyle(document.body).backgroundColor")
            d.screenshot(path=str(SHOTS / "dark.png"), full_page=True)
            assert bg != "rgb(245, 247, 246)", bg
            return f"خلفية الوضع الداكن {bg}"

        def backend_down():
            page.route("**/api/**", lambda r: r.abort())
            page.goto(base + "/sources")
            expect(page.locator(".notice.error[role=alert]")).to_contain_text("تعذّر الاتصال بالخادم")
            assert page.get_by_text("لا توجد مصادر").count() == 0, "تظهر شاشة «لا توجد مصادر» رغم أن الخادم متوقف"
            page.unroute("**/api/**")
            return "رسالة واضحة عند توقف الخلفية"

        step("الدخول بكلمة المرور", login, page)
        step("الحالة الفارغة", empty_state, page)
        step("إعداد الملف ورفع السيرة", profile, page)
        step("التحقق من البريد في النموذج", bad_email, page)
        step("إضافة مصدر وجمعه", add_source, page)
        step("الفرص مرتبة بالتوافق", collect_and_rank, page)
        step("البحث", search_filter, page)
        step("فتح فرصة وتجهيز الرسالة", open_and_draft, page)
        step("تعديل الرسالة وإرسالها", send, page)
        step("صفحة التقديمات", applications, page)
        step("التصفح على الجوال", mobile)
        step("التنقل بلوحة المفاتيح", keyboard)
        step("الوضع الداكن", dark)
        step("تسجيل الخروج", logout, page)
        step("تعطل الخلفية", backend_down, page)
        bad_console = [e for e in console_errors if "Failed to load resource" not in e]
        results.append({"name": "لا أخطاء في سجل المتصفح", "ok": not bad_console, "ms": 0,
                        "detail": "; ".join(bad_console[:3]) or "سجل نظيف", "shot": None})
        print(("✔" if not bad_console else "✘"), "سجل المتصفح:", bad_console[:3] or "نظيف")
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
