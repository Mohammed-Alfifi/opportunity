"use client";

import { useEffect, useState } from "react";
import { api, Profile, Status } from "@/lib/api";

const LIST_FIELDS = ["skills", "target_titles", "locations", "links"] as const;
type ListField = (typeof LIST_FIELDS)[number];
type Form = Omit<Profile, ListField> & Record<ListField, string>;

const join = (xs: string[], sep: string) => xs.join(sep);
const split = (s: string) => s.split(/[،,\n]/).map((x) => x.trim()).filter(Boolean);

export default function ProfilePage() {
  const [form, setForm] = useState<Form | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function fill(p: Profile) {
    setForm({ ...p, skills: join(p.skills, "، "), target_titles: join(p.target_titles, "، "), locations: join(p.locations, "، "), links: join(p.links, "\n") });
  }

  useEffect(() => {
    api<Profile>("/api/profile").then(fill).catch((e) => setMsg({ kind: "error", text: e.message }));
    api<Status>("/api/status").then(setStatus).catch(() => {});
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setBusy(true);
    try {
      const body = { ...form, ...Object.fromEntries(LIST_FIELDS.map((k) => [k, split(form[k])])) };
      fill(await api<Profile>("/api/profile", { method: "PUT", body: JSON.stringify(body) }));
      setMsg({ kind: "ok", text: "حُفظ ملفك وأُعيد تقييم الفرص المفتوحة." });
    } catch (e) {
      setMsg({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try {
      fill(await api<Profile>("/api/profile/cv", { method: "POST", body: fd }));
      setStatus((s) => (s ? { ...s, cv_uploaded: true } : s));
      setMsg({ kind: "ok", text: "رُفعت السيرة الذاتية واستُخرج نصها للتحليل." });
    } catch (err) {
      setMsg({ kind: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  if (!form) return msg ? <p className="notice error">{msg.text}</p> : <p className="muted">جارٍ التحميل...</p>;
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: k === "years_experience" ? Number(e.target.value) : e.target.value });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>ملفي</h1>
          <p>كل تقييم ورسالة تقديم تُبنى على هذه البيانات. كلما كانت أدق كان التحليل أدق.</p>
        </div>
      </div>
      {msg && <p className={`notice ${msg.kind}`} role="status">{msg.text}</p>}

      <div className="detail">
        <form className="panel" onSubmit={save} style={{ display: "grid", gap: 14 }}>
          <div className="grid2">
            <label className="field"><span>الاسم</span><input value={form.full_name} onChange={set("full_name")} /></label>
            <label className="field"><span>المسمى المهني</span><input dir="auto" value={form.headline} onChange={set("headline")} placeholder="Software Engineer | AI & Automation" /></label>
            <label className="field"><span>البريد</span><input className="ltr" type="email" value={form.email} onChange={set("email")} /></label>
            <label className="field"><span>الجوال</span><input className="ltr" value={form.phone} onChange={set("phone")} /></label>
          </div>
          <label className="field"><span>نبذة تظهر في رسائل التقديم</span><textarea rows={3} value={form.summary} onChange={set("summary")} /></label>
          <label className="field"><span>المهارات (افصل بفاصلة)</span><input dir="auto" value={form.skills} onChange={set("skills")} placeholder="Python، FastAPI، Computer Vision، Docker" /></label>
          <label className="field"><span>الوظائف التي تستهدفها</span><input dir="auto" value={form.target_titles} onChange={set("target_titles")} placeholder="AI Engineer، مطور Full-Stack" /></label>
          <div className="grid2">
            <label className="field"><span>المدن المفضلة</span><input value={form.locations} onChange={set("locations")} placeholder="الرياض، Remote" /></label>
            <label className="field"><span>سنوات الخبرة</span><input type="number" min={0} max={50} value={form.years_experience} onChange={set("years_experience")} /></label>
          </div>
          <label className="field"><span>روابط (سطر لكل رابط)</span><textarea className="ltr" rows={2} value={form.links} onChange={set("links")} placeholder="https://github.com/..." /></label>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="primary" disabled={busy}>حفظ الملف</button>
          </div>
        </form>

        <aside className="side">
          <section className="panel">
            <h2 style={{ marginBottom: 8 }}>السيرة الذاتية</h2>
            <p className="small muted">{form.cv_filename ? `الملف الحالي: ${form.cv_filename}` : "لم ترفع سيرتك بعد. تُرفق مع التقديمات ويُقرأ نصها في التحليل."}</p>
            <label className="btn" style={{ display: "inline-block" }}>
              {form.cv_filename ? "استبدل الملف" : "ارفع ملف PDF"}
              <input type="file" accept="application/pdf" onChange={upload} hidden />
            </label>
          </section>
          {status && (
            <section className="panel small">
              <h2 style={{ marginBottom: 8 }}>جاهزية المنصة</h2>
              <ul className="points">
                <li>التحليل العميق: {status.llm.enabled ? `مفعّل (${status.llm.provider})` : "غير مفعّل، يُستخدم التقييم السريع"}</li>
                <li>إرسال البريد: {status.smtp.configured ? `مفعّل من ${status.smtp.user}` : "غير مضبوط"}</li>
                <li>قراءة تنبيهات البريد: {status.imap.configured ? "مفعّلة" : "غير مضبوطة"}</li>
                <li>الجمع التلقائي: {status.collect_interval_minutes ? `كل ${status.collect_interval_minutes} دقيقة` : "متوقف"}</li>
              </ul>
              <p className="muted">تُضبط هذه من ملف <bdi className="ltr-code">.env</bdi> ثم يُعاد تشغيل الخلفية.</p>
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
