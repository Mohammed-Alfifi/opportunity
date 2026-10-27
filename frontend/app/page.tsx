"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ScoreRing from "@/components/ScoreRing";
import { api, Job, JobDetail, STATUS_LABEL, timeAgo } from "@/lib/api";

type Tab = "" | Job["status"];
const TABS: { key: Tab; label: string }[] = [
  { key: "", label: "الكل" },
  { key: "new", label: "جديدة" },
  { key: "shortlisted", label: "مرشحة" },
  { key: "applied", label: "تم التقديم" },
  { key: "ignored", label: "متجاهلة" },
];

export default function OpportunitiesPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("new");
  const [q, setQ] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [sort, setSort] = useState<"score" | "newest">("score");
  const [items, setItems] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ sort, min_score: String(minScore), limit: "100" });
      if (tab) params.set("status", tab);
      if (q.trim()) params.set("q", q.trim());
      const [list, stats] = await Promise.all([
        api<{ total: number; items: Job[] }>(`/api/jobs?${params}`),
        api<{ by_status: Record<string, number> }>("/api/jobs/stats"),
      ]);
      setItems(list.items);
      setTotal(list.total);
      setCounts(stats.by_status);
      setLoadFailed(false);
    } catch (e) {
      setLoadFailed(true);
      setMsg({ kind: "error", text: (e as Error).message });
    } finally {
      setLoading(false);
    }
  }, [tab, q, minScore, sort]);

  useEffect(() => {
    const t = setTimeout(load, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  async function collectNow() {
    setCollecting(true);
    setMsg(null);
    try {
      const r = await api<{ new_jobs: number }>("/api/sources/run-all", { method: "POST" });
      setMsg({ kind: "ok", text: r.new_jobs ? `أُضيفت ${r.new_jobs} فرصة جديدة.` : "لا توجد فرص جديدة الآن. راجع صفحة المصادر إن كان أحدها يعرض خطأ." });
      load();
    } catch (e) {
      setMsg({ kind: "error", text: (e as Error).message });
    } finally {
      setCollecting(false);
    }
  }

  async function setStatus(job: Job, status: Job["status"]) {
    await api(`/api/jobs/${job.id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    load();
  }

  const allCount = Object.entries(counts).filter(([k]) => k !== "ignored").reduce((a, [, v]) => a + v, 0);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>الفرص</h1>
          <p>مرتبة حسب توافقها مع ملفك. افتح أي فرصة لتحليلها وتجهيز رسالة التقديم.</p>
        </div>
        <div className="row">
          <button onClick={() => dialog.current?.showModal()}>إضافة وظيفة</button>
          <button className="primary" onClick={collectNow} disabled={collecting}>
            {collecting ? "جارٍ الجمع..." : "اجمع الآن"}
          </button>
        </div>
      </div>

      {msg && <p className={`notice ${msg.kind}`} role="status">{msg.text}</p>}

      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => setTab(t.key)}>
            {t.label}
            <span className="count">{t.key ? counts[t.key] ?? 0 : allCount}</span>
          </button>
        ))}
      </div>

      <div className="filters">
        <input type="search" placeholder="ابحث في المسمى أو الجهة أو الوصف" value={q} onChange={(e) => setQ(e.target.value)} aria-label="بحث" />
        <select value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} aria-label="أقل توافق">
          <option value={0}>كل درجات التوافق</option>
          <option value={45}>45% فأكثر</option>
          <option value={60}>60% فأكثر</option>
          <option value={70}>70% فأكثر</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as "score" | "newest")} aria-label="الترتيب">
          <option value="score">الأعلى توافقاً</option>
          <option value="newest">الأحدث</option>
        </select>
      </div>

      {loadFailed && !items.length ? null : loading && !items.length ? (
        <p className="muted">جارٍ التحميل...</p>
      ) : !items.length ? (
        <div className="jobs empty">
          <h2>{allCount ? "لا توجد فرص بهذا الفرز" : "لا توجد فرص بعد"}</h2>
          <p>{allCount ? "غيّر التبويب أو خفّض حد التوافق." : "أضف مصادرك أولاً (قنوات تيليجرام، مواقع التوظيف، تنبيهات البريد)، ثم اضغط «اجمع الآن»."}</p>
          {!allCount && <Link href="/sources">إضافة المصادر</Link>}
        </div>
      ) : (
        <>
          <p className="small muted">{total} فرصة</p>
          <div className="jobs">
            {items.map((j) => (
              <article className="job" key={j.id}>
                <ScoreRing score={j.score} />
                <div>
                  <h3><Link href={`/jobs?id=${j.id}`} dir="auto">{j.title}</Link></h3>
                  <div className="meta">
                    {j.company && <span dir="auto">{j.company}</span>}
                    {j.location && <span dir="auto">{j.location}</span>}
                    <span>{j.source_name}</span>
                    <span>{timeAgo(j.posted_at || j.created_at)}</span>
                    {j.status !== "new" && <span className="chip">{STATUS_LABEL[j.status]}</span>}
                    {j.contact_email && <span className="chip good">بريد للتقديم</span>}
                  </div>
                </div>
                <div className="actions">
                  {j.status === "new" && <button className="ghost" onClick={() => setStatus(j, "shortlisted")}>رشّحها</button>}
                  {j.status !== "ignored" && j.status !== "applied" && (
                    <button className="ghost" onClick={() => setStatus(j, "ignored")}>تجاهل</button>
                  )}
                  {j.status === "ignored" && <button className="ghost" onClick={() => setStatus(j, "new")}>استرجاع</button>}
                </div>
              </article>
            ))}
          </div>
        </>
      )}

      <AddJobDialog ref={dialog} onAdded={(j) => router.push(`/jobs?id=${j.id}`)} />
    </>
  );
}

function AddJobDialog({ ref, onAdded }: { ref: React.Ref<HTMLDialogElement>; onAdded: (j: JobDetail) => void }) {
  const [mode, setMode] = useState<"url" | "manual">("url");
  const [url, setUrl] = useState("");
  const [form, setForm] = useState({ title: "", company: "", location: "", description: "", contact_email: "", url: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const job =
        mode === "url"
          ? await api<JobDetail>("/api/jobs/import-url", { method: "POST", body: JSON.stringify({ url }) })
          : await api<JobDetail>("/api/jobs", {
              method: "POST",
              body: JSON.stringify(Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v || null]))),
            });
      onAdded(job);
    } catch (e) {
      setErr((e as Error).message);
      if (mode === "url") setMode("manual");
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <dialog ref={ref} aria-labelledby="add-title">
      <form onSubmit={submit} style={{ display: "grid", gap: 14 }}>
        <h2 id="add-title">إضافة وظيفة</h2>
        <div className="tabs">
          <button type="button" className={mode === "url" ? "on" : ""} onClick={() => setMode("url")}>من رابط</button>
          <button type="button" className={mode === "manual" ? "on" : ""} onClick={() => setMode("manual")}>نسخ ولصق</button>
        </div>
        {err && <p className="notice error">{err}</p>}
        {mode === "url" ? (
          <label className="field">
            <span>رابط الإعلان</span>
            <input className="ltr" type="url" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
            صفحات لينكدإن وبعض المواقع تتطلب تسجيل دخول؛ إن فشل الجلب الصق نص الإعلان يدوياً.
          </label>
        ) : (
          <>
            <label className="field"><span>المسمى</span><input required value={form.title} onChange={set("title")} /></label>
            <div className="grid2">
              <label className="field"><span>الجهة</span><input value={form.company} onChange={set("company")} /></label>
              <label className="field"><span>المدينة</span><input value={form.location} onChange={set("location")} /></label>
            </div>
            <label className="field"><span>نص الإعلان</span><textarea rows={7} value={form.description} onChange={set("description")} /></label>
            <div className="grid2">
              <label className="field"><span>بريد التقديم</span><input className="ltr" type="email" value={form.contact_email} onChange={set("contact_email")} /></label>
              <label className="field"><span>الرابط</span><input className="ltr" type="url" value={form.url} onChange={set("url")} /></label>
            </div>
          </>
        )}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="ghost" onClick={(e) => (e.currentTarget.closest("dialog") as HTMLDialogElement).close()}>إلغاء</button>
          <button className="primary" disabled={busy}>{busy ? "جارٍ الإضافة..." : "أضف الوظيفة"}</button>
        </div>
      </form>
    </dialog>
  );
}
