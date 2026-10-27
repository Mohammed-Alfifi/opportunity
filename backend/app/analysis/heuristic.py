"""تقييم توافق سريع بدون نموذج لغوي: مطابقة المهارات والمسمى والمدينة والخبرة."""
from __future__ import annotations

import re

# مصطلحات تقنية شائعة؛ إن ظهرت في الإعلان وليست في ملفك تُعرض كفجوات
TECH_VOCAB = [
    "python", "java", "javascript", "typescript", "c#", ".net", "go", "golang", "rust", "php", "kotlin", "swift",
    "react", "next.js", "angular", "vue", "node.js", "django", "fastapi", "flask", "spring", "laravel",
    "flutter", "react native", "android", "ios",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "oracle",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "linux", "ci/cd", "devops",
    "machine learning", "deep learning", "computer vision", "nlp", "llm", "pytorch", "tensorflow", "opencv",
    "yolo", "data analysis", "power bi", "tableau", "etl", "spark",
    "microservices", "rest", "graphql", "git", "agile", "scrum", "cybersecurity", "sap", "salesforce",
]
SAUDI_CITIES = {
    "riyadh": "الرياض", "jeddah": "جدة", "dammam": "الدمام", "khobar": "الخبر", "makkah": "مكة",
    "madinah": "المدينة", "jazan": "جازان", "abha": "أبها", "tabuk": "تبوك", "qassim": "القصيم",
    "dhahran": "الظهران", "neom": "نيوم", "remote": "عن بعد",
}
# مرادفات عربية/إنجليزية: إعلان عربي ومسمى مستهدف بالإنجليزية (أو العكس) يجب أن يتطابقا
SYNONYMS = [
    ("رؤية حاسوبية", "computer vision"), ("الرؤية الحاسوبية", "computer vision"),
    ("ذكاء اصطناعي", "ai"), ("الذكاء الاصطناعي", "ai"), ("تعلم الآلة", "machine learning"),
    ("التعلم العميق", "deep learning"), ("معالجة اللغة", "nlp"), ("تحليل البيانات", "data analysis"),
    ("علم البيانات", "data science"), ("بيانات", "data"), ("مطور", "developer"), ("مبرمج", "developer"),
    ("مهندس", "engineer"), ("برمجيات", "software"), ("تطبيقات الجوال", "mobile"), ("واجهات", "frontend"),
    ("الواجهة الخلفية", "backend"), ("قواعد البيانات", "database"), ("أمن سيبراني", "cybersecurity"),
    ("الأمن السيبراني", "cybersecurity"), ("شبكات", "network"), ("سحابية", "cloud"), ("حوسبة سحابية", "cloud"),
    ("أتمتة", "automation"), ("كبير", "senior"), ("أول", "senior"), ("متدرب", "intern"),
    ("عن بعد", "remote"), ("الرياض", "riyadh"), ("جدة", "jeddah"), ("الدمام", "dammam"), ("الخبر", "khobar"),
]


def bilingual(text: str) -> str:
    t = (text or "").lower()
    extra = [en for ar, en in SYNONYMS if ar in t] + [ar for ar, en in SYNONYMS if _contains(t, en)]
    return t + ("\n" + " ".join(extra) if extra else "")


YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|to|إلى)?\s*\d{0,2}\s*(?:years?|yrs|سنوات|سنة|عام|أعوام)", re.I)


def _contains(hay: str, term: str) -> bool:
    term = term.lower().strip()
    if not term:
        return False
    if re.search(r"[a-z]", term) and len(term) <= 4:
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", hay) is not None
    return term in hay


def required_years(text: str) -> int | None:
    nums = [int(m.group(1)) for m in YEARS_RE.finditer(text or "") if 0 < int(m.group(1)) < 30]
    return min(nums) if nums else None


def analyze(job: dict, profile: dict) -> dict:
    hay = bilingual(f"{job.get('title', '')}\n{job.get('description', '')}\n{job.get('location') or ''}")
    title = bilingual(job.get("title") or "")
    skills = [s for s in profile.get("skills", []) if s.strip()]
    titles = [t for t in profile.get("target_titles", []) if t.strip()]
    locations = [l for l in profile.get("locations", []) if l.strip()]

    matched = [s for s in skills if _contains(hay, s)]
    skill_lower = {s.lower() for s in skills}
    gaps = [t for t in TECH_VOCAB if _contains(hay, t) and t not in skill_lower][:8]

    # المهارات 50، المسمى 25، المدينة 10، الخبرة 15
    mentioned = len(matched) + len(gaps)
    skill_score = 50 * (len(matched) / mentioned) if mentioned else (25 if matched else 15)
    title_score = 0.0
    if titles:
        best = 0.0
        for t in titles:
            words = [w for w in re.split(r"[\s/|,-]+", t.lower()) if len(w) > 2]
            if words:
                best = max(best, sum(w in title for w in words) / len(words))
        title_score = 25 * best
    loc_score = 5.0
    if locations:
        loc_terms = set()
        for l in locations:
            loc_terms.add(l.lower())
            for en, ar in SAUDI_CITIES.items():
                if l.lower() in (en, ar):
                    loc_terms.update({en, ar})
        loc_score = 10.0 if any(t in hay for t in loc_terms) else 2.0
    req = required_years(hay)
    yrs = int(profile.get("years_experience") or 0)
    if req is None:
        exp_score = 10.0
    elif yrs >= req:
        exp_score = 15.0
    else:
        exp_score = max(0.0, 15.0 - 5.0 * (req - yrs))

    score = round(min(100, skill_score + title_score + loc_score + exp_score))
    strengths = [f"مهارة مطلوبة لديك: {s}" for s in matched[:6]]
    if title_score >= 15:
        strengths.append("المسمى قريب من الوظائف التي تستهدفها")
    concerns = []
    if gaps:
        concerns.append("مذكور في الإعلان وغير موجود في ملفك: " + "، ".join(gaps))
    if req and yrs < req:
        concerns.append(f"الإعلان يطلب حوالي {req} سنوات خبرة ولديك {yrs}")
    if locations and loc_score < 10:
        concerns.append("المدينة قد لا تطابق مدنك المفضلة")
    if score >= 70:
        rec = "قدّم"
    elif score >= 45:
        rec = "راجع قبل التقديم"
    else:
        rec = "تجاهل غالباً"
    return {
        "engine": "heuristic",
        "score": score,
        "recommendation": rec,
        "summary": f"توافق تقريبي {score}% بناءً على المهارات والمسمى والمدينة والخبرة.",
        "matched_skills": matched,
        "missing_skills": gaps,
        "strengths": strengths,
        "concerns": concerns,
        "required_years": req,
    }
