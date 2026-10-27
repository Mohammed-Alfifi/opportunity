"""عالم وهمي للاختبار: خادم ويب يحاكي مصادر الوظائف ونموذج اللغة، وخادم بريد SMTP يستقبل الرسائل فعلياً."""
from __future__ import annotations

import json
import threading
from email import message_from_bytes, policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TELEGRAM = """<html><body>
<div class="tgme_widget_message">
 <div class="tgme_widget_message_text">💼 مطلوب مهندس رؤية حاسوبية - الرياض<br>خبرة سنتين في Python و OpenCV و Docker<br>
 أرسل سيرتك إلى: talent@vision.sa <a href="https://vision.sa/jobs/cv-01?utm_source=tg">التفاصيل</a></div>
 <a class="tgme_widget_message_date" href="https://t.me/ksa_tech/501"><time datetime="2026-10-26T09:00:00+00:00"></time></a>
</div>
<div class="tgme_widget_message">
 <div class="tgme_widget_message_text">مطلوب مطور Full-Stack عن بعد<br>React و FastAPI و PostgreSQL، خبرة 3 سنوات<br>
 للتواصل: jobs@stack.sa</div>
 <a class="tgme_widget_message_date" href="https://t.me/ksa_tech/502"><time datetime="2026-10-26T11:30:00+00:00"></time></a>
</div>
<div class="tgme_widget_message">
 <div class="tgme_widget_message_text">مطلوب سائق خاص لعائلة في جدة، رخصة سارية وراتب ممتاز</div>
 <a class="tgme_widget_message_date" href="https://t.me/ksa_tech/503"><time datetime="2026-10-26T12:00:00+00:00"></time></a>
</div>
</body></html>"""

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Tech Jobs KSA</title>
<item><title>Computer Vision Engineer</title><link>https://vision.sa/jobs/cv-01</link>
<description>Same role as the Telegram post (duplicate by URL).</description><pubDate>Mon, 26 Oct 2026 08:00:00 GMT</pubDate></item>
<item><title>Machine Learning Engineer - Riyadh</title><link>https://ml.sa/careers/42?utm_campaign=x</link>
<description>&lt;p&gt;PyTorch, Python, LLM experience. 4+ years. Apply: careers@ml.sa&lt;/p&gt;</description>
<pubDate>Tue, 27 Oct 2026 06:00:00 GMT</pubDate></item>
</channel></rss>"""

CAREERS = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"ItemList","itemListElement":[
 {"@type":"ListItem","item":{"@type":"JobPosting","title":"مهندس ذكاء اصطناعي",
  "description":"<p>تطوير نماذج تحليل الفيديو باستخدام Python و YOLO. خبرة سنتين. الرياض.</p>",
  "hiringOrganization":{"@type":"Organization","name":"هيئة تقنية"},"datePosted":"2026-10-25",
  "url":"https://gov-tech.sa/careers/ai-7","jobLocation":{"@type":"Place","address":{"addressLocality":"الرياض","addressCountry":"SA"}}}},
 {"@type":"ListItem","item":{"@type":"JobPosting","title":"SAP Consultant",
  "description":"SAP FICO 8 years.","hiringOrganization":{"@type":"Organization","name":"هيئة تقنية"},
  "url":"https://gov-tech.sa/careers/sap-2","jobLocationType":"TELECOMMUTE"}}
]}</script></head><body></body></html>"""

SINGLE = """<html><head><meta property="og:title" content="Senior Backend Engineer – Fintech">
<meta property="og:site_name" content="PayCo"></head><body><nav>menu</nav><main>
We are hiring a backend engineer: Python, FastAPI, PostgreSQL, Redis, Docker. 3+ years. Riyadh or remote.
Send your CV to hiring@payco.sa</main></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    llm_calls: list = []

    def log_message(self, *a):  # صامت
        pass

    def _send(self, body: str | bytes, ctype="text/html; charset=utf-8", code=200):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # العميل أغلق الاتصال عند انتهاء المهلة، وهذا هو المقصود في اختبار البطء

    def do_GET(self):  # noqa: N802
        routes = {
            "/s/ksa_tech": (TELEGRAM, "text/html; charset=utf-8"),
            "/feed.xml": (RSS, "application/rss+xml"),
            "/careers": (CAREERS, "text/html; charset=utf-8"),
            "/job/single": (SINGLE, "text/html; charset=utf-8"),
            "/empty": ("<html><body>no jobs</body></html>", "text/html"),
        }
        path = self.path.split("?")[0]
        if path in routes:
            return self._send(*routes[path])
        if path == "/big":
            return self._send(b"<html>" + b"x" * (6 * 1024 * 1024) + b"</html>")
        if path == "/slow":
            import time
            time.sleep(3)
            return self._send("<html></html>")
        self._send("not found", code=404)

    def do_POST(self):  # noqa: N802 — نموذج لغة متوافق مع OpenAI
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        prompt = req["messages"][-1]["content"]
        _Handler.llm_calls.append(prompt)
        if "score (0-100)" in prompt:
            content = json.dumps({
                "score": 88, "recommendation": "قدّم",
                "summary": "توافق قوي في Python والرؤية الحاسوبية.",
                "strengths": ["خبرة عملية في الرؤية الحاسوبية"], "concerns": ["لا ذكر لـ OpenCV في الملف"],
                "missing_skills": ["OpenCV"], "matched_skills": ["Python", "Docker"],
                "tips": ["اذكر مشروع تحليل الكاميرات"], "company": "Vision Co", "location": "الرياض"}, ensure_ascii=False)
        else:
            content = "إليك الرسالة:\n" + json.dumps({"subject": "تقديم: مهندس رؤية حاسوبية",
                                                     "body": "السلام عليكم،\nأتقدم لوظيفة مهندس رؤية حاسوبية...\nمحمد"},
                                                    ensure_ascii=False)
        self._send(json.dumps({"choices": [{"message": {"content": content}}]}), "application/json")


class MockWeb:
    def __init__(self, port: int):
        self.server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self.url = f"http://127.0.0.1:{port}"
        self.llm_calls = _Handler.llm_calls

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()


class MockSMTP:
    def __init__(self, port: int):
        from aiosmtpd.controller import Controller

        self.messages: list = []
        outer = self

        class H:
            async def handle_DATA(self, server, session, envelope):  # noqa: N802
                outer.messages.append({"rcpt": envelope.rcpt_tos, "msg": message_from_bytes(envelope.content, policy=policy.default)})
                return "250 OK"

        self.controller = Controller(H(), hostname="127.0.0.1", port=port)

    def __enter__(self):
        self.controller.start()
        return self

    def __exit__(self, *a):
        self.controller.stop()
