"""تحليل الفرصة وتجهيز رسالة التقديم."""
from __future__ import annotations

from ..collectors.base import detect_lang
from . import heuristic, llm

ANALYZE_SYSTEM = (
    "أنت مستشار توظيف تقني في السوق السعودي. تقيّم توافق مرشح مع إعلان وظيفة بدقة وصراحة، "
    "بدون مجاملة. أجب بـ JSON فقط."
)
LETTER_SYSTEM = (
    "أنت تكتب رسائل تقديم وظيفي قصيرة ومقنعة باسم المرشح. لا تخترع خبرات أو شهادات غير موجودة في ملفه. "
    "أجب بـ JSON فقط."
)


def profile_brief(profile: dict) -> str:
    return (
        f"الاسم: {profile.get('full_name')}\n"
        f"المسمى: {profile.get('headline')}\n"
        f"سنوات الخبرة: {profile.get('years_experience')}\n"
        f"المهارات: {', '.join(profile.get('skills', []))}\n"
        f"الوظائف المستهدفة: {', '.join(profile.get('target_titles', []))}\n"
        f"المدن المفضلة: {', '.join(profile.get('locations', []))}\n"
        f"نبذة: {profile.get('summary')}\n"
        f"السيرة الذاتية (مقتطف):\n{(profile.get('cv_text') or '')[:5000]}"
    )


def job_brief(job: dict) -> str:
    return (
        f"المسمى: {job.get('title')}\nالجهة: {job.get('company') or 'غير مذكورة'}\n"
        f"المدينة: {job.get('location') or 'غير مذكورة'}\n"
        f"الوصف:\n{(job.get('description') or '')[:6000]}"
    )


def analyze(job: dict, profile: dict, use_llm: bool = True) -> dict:
    base = heuristic.analyze(job, profile)
    if not (use_llm and llm.enabled()):
        return base
    prompt = (
        f"ملف المرشح:\n{profile_brief(profile)}\n\n---\nالإعلان:\n{job_brief(job)}\n\n"
        "أرجع JSON بالمفاتيح: score (0-100)، recommendation (قدّم | راجع قبل التقديم | تجاهل غالباً)، "
        "summary (جملتان بالعربية)، strengths (قائمة)، concerns (قائمة)، missing_skills (قائمة)، "
        "matched_skills (قائمة)، tips (قائمة نصائح محددة لتخصيص التقديم)، "
        "company (اسم الجهة إن عُرف من النص أو null)، location (المدينة أو null)."
    )
    try:
        data = llm.complete_json(ANALYZE_SYSTEM, prompt)
    except llm.LLMError as e:
        base["llm_error"] = str(e)
        return base
    out = {**base, **{k: v for k, v in data.items() if v not in (None, "", [])}, "engine": "llm"}
    try:
        out["score"] = max(0, min(100, int(out["score"])))
    except (TypeError, ValueError):
        out["score"] = base["score"]
    out["heuristic_score"] = base["score"]
    return out


def _template_letter(job: dict, profile: dict, analysis: dict, lang: str) -> dict:
    name = profile.get("full_name") or ""
    title = job.get("title") or ""
    company = job.get("company")
    skills = (analysis.get("matched_skills") or profile.get("skills", []))[:5]
    yrs = profile.get("years_experience") or 0
    contact = " | ".join(x for x in [profile.get("phone"), profile.get("email")] if x)
    links = "\n".join(profile.get("links", []))
    summary = profile.get("summary") or ""
    if lang == "en" and detect_lang(summary) == "ar":
        summary = ""  # لا نخلط نبذة عربية داخل رسالة إنجليزية
    profile = {**profile, "summary": summary}
    if lang == "en":
        subject = f"Application: {title}" + (f" – {name}" if name else "")
        body = (
            f"Dear Hiring Team{' at ' + company if company else ''},\n\n"
            f"I am writing to apply for the {title} position. "
            f"I am a {profile.get('headline') or 'software professional'} with {yrs} years of experience"
            + (f", working with {', '.join(skills)}" if skills else "") + ".\n\n"
            f"{profile.get('summary') or ''}\n\n"
            "I would welcome the opportunity to discuss how I can contribute to your team. "
            "My CV is attached for your review.\n\n"
            f"Best regards,\n{name}\n{contact}\n{links}"
        )
    else:
        subject = f"طلب التقديم على وظيفة: {title}" + (f" – {name}" if name else "")
        body = (
            f"السلام عليكم ورحمة الله وبركاته،\n\n"
            f"فريق التوظيف{' في ' + company if company else ''} المحترم،\n\n"
            f"أتقدم بطلب للانضمام إليكم في وظيفة «{title}». "
            f"أعمل {profile.get('headline') or 'في المجال التقني'} بخبرة {yrs} سنوات"
            + (f"، وأملك خبرة عملية في {('، '.join(skills))}" if skills else "") + ".\n\n"
            f"{profile.get('summary') or ''}\n\n"
            "يسعدني التواصل معكم لمناقشة كيف يمكنني الإسهام في فريقكم، ومرفق سيرتي الذاتية.\n\n"
            f"وتقبلوا خالص التحية،\n{name}\n{contact}\n{links}"
        )
    return {"subject": subject, "body": body.strip(), "engine": "template"}


def write_letter(job: dict, profile: dict, analysis: dict | None, lang: str, use_llm: bool = True,
                 instructions: str = "") -> dict:
    analysis = analysis or heuristic.analyze(job, profile)
    if not (use_llm and llm.enabled()):
        return _template_letter(job, profile, analysis, lang)
    language = "العربية الفصحى المهنية" if lang == "ar" else "English (professional)"
    prompt = (
        f"ملف المرشح:\n{profile_brief(profile)}\n\n---\nالإعلان:\n{job_brief(job)}\n\n"
        f"نقاط القوة المكتشفة: {analysis.get('strengths')}\n\n"
        f"اكتب رسالة تقديم بريدية باللغة: {language}. 120 إلى 220 كلمة، تربط 2-3 خبرات حقيقية من ملفه "
        "بمتطلبات الإعلان، بلا عبارات عامة مكررة، وتختم بالاسم ووسائل التواصل. "
        f"{('تعليمات إضافية من المرشح: ' + instructions) if instructions else ''}\n"
        "أرجع JSON بالمفتاحين: subject، body."
    )
    try:
        data = llm.complete_json(LETTER_SYSTEM, prompt)
        if data.get("body"):
            return {"subject": data.get("subject") or job.get("title"), "body": data["body"], "engine": "llm"}
    except llm.LLMError as e:
        out = _template_letter(job, profile, analysis, lang)
        out["llm_error"] = str(e)
        return out
    return _template_letter(job, profile, analysis, lang)
