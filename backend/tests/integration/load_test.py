"""اختبار حمل وتزامن على خادم حي.

python tests/integration/load_test.py [--backend PATH] [--jobs 5000]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from mock_world import MockWeb  # noqa: E402

H = {"x-forsa-client": "web"}


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * p))], 1)


def timed(c, method, url, **kw):
    t = time.perf_counter()
    r = c.request(method, url, **kw)
    return (time.perf_counter() - t) * 1000, r.status_code


def seed(backend: Path, data_dir: str, n: int):
    """إدخال n وظيفة مباشرة في القاعدة (أسرع من الواجهة) بنصوص واقعية الطول."""
    code = f"""
import random, sys
sys.path.insert(0, {str(backend)!r})
from app.db import init_db, SessionLocal
from app.models import Job
from app.analysis import heuristic
init_db()
random.seed(7)
titles = ["Python Developer", "مهندس ذكاء اصطناعي", "Data Analyst", "مطور Full-Stack", "DevOps Engineer",
          "محاسب", "Computer Vision Engineer", "مدير مشاريع", "Backend Engineer", "مهندس شبكات"]
words = "Python FastAPI Docker React SQL Kubernetes AWS Java Spark OpenCV الرياض جدة خبرة سنوات فريق مشاريع تطوير".split()
P = {{"skills": ["Python", "FastAPI", "Docker", "React"], "target_titles": ["Backend Engineer"], "locations": ["الرياض"], "years_experience": 3}}
with SessionLocal() as s:
    for i in range({n}):
        t = random.choice(titles)
        d = " ".join(random.choice(words) for _ in range(180))
        a = heuristic.analyze({{"title": t, "description": d}}, P)
        s.add(Job(fingerprint=f"seed-{{i}}", title=f"{{t}} #{{i}}", description=d, score=a["score"], analysis=a,
                  status=random.choice(["new"] * 6 + ["shortlisted", "applied", "ignored"])))
        if i % 1000 == 999:
            s.commit()
    s.commit()
"""
    subprocess.run([sys.executable, "-c", code], env={**os.environ, "DATA_DIR": data_dir}, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--jobs", type=int, default=5000)
    ap.add_argument("--port", type=int, default=8200)
    ap.add_argument("--out")
    args = ap.parse_args()
    backend = Path(args.backend)
    data_dir = tempfile.mkdtemp(prefix="forsa-load-")
    out: dict = {"backend": str(backend)}

    t = time.perf_counter()
    seed(backend, data_dir, args.jobs)
    out["seed_s"] = round(time.perf_counter() - t, 1)

    with MockWeb(args.port + 1) as web:
        env = {**os.environ, "DATA_DIR": data_dir, "SCHEDULER_ENABLED": "false", "ALLOW_PRIVATE_NETWORK": "true",
               "TELEGRAM_BASE_URL": f"{web.url}/s"}
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(args.port)],
                                cwd=backend, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        base = f"http://127.0.0.1:{args.port}"
        try:
            for _ in range(60):
                try:
                    httpx.get(base + "/api/health")
                    break
                except httpx.HTTPError:
                    time.sleep(0.2)
            c = httpx.Client(base_url=base, headers=H, timeout=60)

            # 1) زمن الاستجابة لعمليات القراءة الشائعة، 200 طلب لكل واحدة
            scenarios = {
                "قائمة الفرص (الأحدث)": ("GET", "/api/jobs", {"params": {"limit": 100}}),
                "قائمة الفرص (حسب التوافق)": ("GET", "/api/jobs", {"params": {"limit": 100, "sort": "score"}}),
                "بحث نصي": ("GET", "/api/jobs", {"params": {"q": "Docker", "limit": 100}}),
                "فلتر التوافق 70+": ("GET", "/api/jobs", {"params": {"min_score": 70, "limit": 100}}),
                "تفاصيل وظيفة": ("GET", "/api/jobs/2500", {}),
                "الإحصائيات": ("GET", "/api/jobs/stats", {}),
            }
            out["latency"] = {}
            for name, (m, u, kw) in scenarios.items():
                xs = [timed(c, m, u, **kw)[0] for _ in range(200)]
                out["latency"][name] = {"p50": pct(xs, 0.5), "p95": pct(xs, 0.95), "max": round(max(xs), 1)}
                print(name, out["latency"][name])

            # 2) إعادة تقييم كل الوظائف بعد تعديل الملف الشخصي
            t = time.perf_counter()
            r = c.put("/api/profile", json={"skills": ["Python", "Docker", "Kubernetes"], "target_titles": ["DevOps Engineer"]})
            out["rescore_ms"] = round((time.perf_counter() - t) * 1000)
            out["rescore_status"] = r.status_code
            print("إعادة التقييم", out["rescore_ms"], "ms")

            # 3) حمل متوازي: 20 مستخدماً افتراضياً × 50 طلباً
            lat, codes = [], []
            lock = threading.Lock()

            def worker(_):
                with httpx.Client(base_url=base, headers=H, timeout=60) as cc:
                    for k in range(50):
                        ms, code = timed(cc, "GET", "/api/jobs", params={"limit": 50, "sort": "score" if k % 2 else "newest"})
                        with lock:
                            lat.append(ms)
                            codes.append(code)

            t = time.perf_counter()
            with ThreadPoolExecutor(20) as ex:
                list(ex.map(worker, range(20)))
            dur = time.perf_counter() - t
            out["concurrent"] = {"requests": len(codes), "errors": sum(c_ != 200 for c_ in codes),
                                 "rps": round(len(codes) / dur), "p50": pct(lat, 0.5), "p95": pct(lat, 0.95)}
            print("حمل متوازي", out["concurrent"])

            # 4) جمع متزامن لنفس المصدر (الجمع الدوري + ضغط زر الجمع في نفس اللحظة)
            sid = c.post("/api/sources", json={"name": "t", "kind": "telegram", "config": {"channel": "ksa_tech"}}).json()["id"]
            res = []

            def run_src(_):
                with httpx.Client(base_url=base, headers=H, timeout=60) as cc:
                    r = cc.post(f"/api/sources/{sid}/run")
                    res.append((r.status_code, r.json().get("last_new_count") if r.status_code == 200 else None))

            with ThreadPoolExecutor(4) as ex:
                list(ex.map(run_src, range(4)))
            total = c.get("/api/jobs", params={"q": "رؤية حاسوبية"}).json()["total"]
            out["concurrent_collect"] = {"responses": sorted(res, key=str), "server_errors": sum(s >= 500 for s, _ in res),
                                         "stored_copies_of_one_job": total}
            print("جمع متزامن", out["concurrent_collect"])
            c.close()
        finally:
            proc.terminate()
            err = proc.stderr.read().decode(errors="replace")
            proc.wait(5)
            out["server_tracebacks"] = err.count("Traceback")
            out["integrity_errors_in_log"] = err.count("IntegrityError")
    out["db_size_mb"] = round(Path(data_dir, "forsa.db").stat().st_size / 1e6, 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
