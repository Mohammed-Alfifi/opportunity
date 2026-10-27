from app.collectors import imap, rss, telegram, webpage
from app.collectors.base import RawJob, detect_lang, extract_email, fingerprint, passes_filters

TG_HTML = """
<div class="tgme_widget_message">
  <div class="tgme_widget_message_text">💼 مطلوب مطور Python في الرياض<br>
  خبرة 3 سنوات في FastAPI و PostgreSQL<br>
  للتقديم: hr@company.sa <a href="https://apply.company.sa/job/1">رابط التقديم</a></div>
  <a class="tgme_widget_message_date" href="https://t.me/jobs_ksa/101"><time datetime="2026-10-25T10:00:00+00:00"></time></a>
</div>
<div class="tgme_widget_message"><div class="tgme_widget_message_text">قصير</div></div>
"""

JSONLD_HTML = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"JobPosting","title":"Backend Engineer",
"description":"<p>Build APIs with <b>Python</b> and Docker. 2+ years.</p>",
"hiringOrganization":{"@type":"Organization","name":"Acme KSA"},
"datePosted":"2026-10-20","url":"https://acme.sa/careers/1",
"jobLocation":{"@type":"Place","address":{"addressLocality":"Riyadh","addressCountry":"SA"}}}]}
</script></head><body></body></html>
"""

RSS_XML = """<?xml version="1.0"?><rss version="2.0"><channel><title>Jobs</title>
<item><title>Data Analyst - Jeddah</title><link>https://jobs.example/1?utm_source=rss</link>
<description>&lt;p&gt;SQL and Power BI&lt;/p&gt;</description><pubDate>Mon, 26 Oct 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""

ALERT_HTML = """
<table><tr><td>
  <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc&refId=x">Senior AI Engineer</a>
  <p>Anan Alsamaa</p><p>Dammam, Eastern Province</p>
</td></tr><tr><td><a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trk=1">View job</a></td></tr></table>
"""


def test_telegram_parse():
    jobs = telegram.parse_channel(TG_HTML)
    assert len(jobs) == 1
    j = jobs[0]
    assert "مطور Python" in j.title
    assert j.url == "https://t.me/jobs_ksa/101"
    assert j.extra["apply_url"] == "https://apply.company.sa/job/1"
    assert extract_email(j.description) == "hr@company.sa"
    assert telegram.channel_url("@jobs_ksa") == "https://t.me/s/jobs_ksa"
    assert telegram.channel_url("https://t.me/jobs_ksa") == "https://t.me/s/jobs_ksa"


def test_jsonld_parse():
    jobs = webpage.parse_page(JSONLD_HTML, "https://acme.sa/careers")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Backend Engineer" and j.company == "Acme KSA"
    assert "Riyadh" in j.location and "Python" in j.description


def test_single_page_fallback():
    html = '<html><head><meta property="og:title" content="مهندس شبكات"></head><body><main>' + "وصف " * 50 + "</main></body></html>"
    j = webpage.parse_single(html, "https://x.sa/j")
    assert j.title == "مهندس شبكات" and j.description


def test_rss_parse_and_url_normalization():
    jobs = rss.parse_feed(RSS_XML)
    assert jobs[0].title == "Data Analyst - Jeddah"
    assert jobs[0].description == "SQL and Power BI"
    a = RawJob(title="x", url="https://jobs.example/1?utm_source=rss")
    b = RawJob(title="y", url="https://JOBS.example/1/")
    assert fingerprint(a) == fingerprint(b)


def test_imap_alert_parse_dedupes_links():
    jobs = imap.parse_alert_email(ALERT_HTML, "LinkedIn", None)
    assert len(jobs) == 1
    assert jobs[0].title == "Senior AI Engineer"
    assert jobs[0].company == "Anan Alsamaa"
    assert "trackingId" not in jobs[0].url


def test_filters_and_lang():
    j = RawJob(title="مطلوب محاسب", description="")
    assert not passes_filters(j, {"include_keywords": ["مطور", "developer"]})
    assert passes_filters(j, {"exclude_keywords": ["سائق"]})
    assert detect_lang("مطلوب مطور Python") == "ar"
    assert detect_lang("We are hiring a Python developer") == "en"


def test_cross_source_duplicate_by_apply_link():
    tg = RawJob(title="مطلوب مهندس", description="نص تيليجرام", url="https://t.me/ch/5",
                extra={"apply_url": "https://co.sa/jobs/1?utm_source=tg"})
    feed = RawJob(title="Engineer", description="RSS text", url="https://co.sa/jobs/1")
    assert fingerprint(tg) == fingerprint(feed)
