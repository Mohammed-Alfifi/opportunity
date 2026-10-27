"use client";

import { useEffect, useRef, useState } from "react";
import { api, Source, timeAgo } from "@/lib/api";

type Kind = Source["kind"];
const KINDS: { kind: Kind; label: string; hint: string }[] = [
  { kind: "telegram", label: "قناة تيليجرام", hint: "اسم قناة عامة مثل @saudi_jobs. تُقرأ رسائلها الأخيرة بدون تسجيل دخول." },
  { kind: "rss", label: "خلاصة RSS", hint: "رابط خلاصة RSS أو Atom من موقع توظيف أو صفحة وظائف شركة." },
  { kind: "webpage", label: "صفحة وظائف", hint: "صفحة توظيف شركة أو جهة حكومية تنشر وظائفها ببيانات JobPosting المنظمة." },
  { kind: "imap", label: "تنبيهات البريد", hint: "تقرأ رسائل تنبيهات الوظائف من بريدك: لينكدإن وجدارات وبيت وغيرها. فعّل التنبيهات في حساباتك أولاً." },
];
const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.kind, k.label])) as Record<Kind, string>;

const EMPTY = { name: "", kind: "telegram" as Kind, target: "", senders: "jobalerts-noreply@linkedin.com", include: "", exclude: "", days: 3 };

function toForm(s: Source) {
  const c = s.config as Record<string, unknown>;
  return {
    name: s.name,
    kind: s.kind,
    target: String(c.channel ?? c.url ?? ""),
    senders: ((c.senders as string[]) ?? []).join("\n"),
    include: ((c.include_keywords as string[]) ?? []).join("، "),
    exclude: ((c.exclude_keywords as string[]) ?? []).join("، "),
    days: Number(c.days ?? 3),
  };
}

const splitWords = (s: string) => s.split(/[،,\n]/).map((x) => x.trim()).filter(Boolean);

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState<number | null>(null);
  const [running, setRunning] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);

  const load = () =>
    api<Source[]>("/api/sources")
      .then((r) => {
        setSources(r);
        setErr("");
      })
      .catch((e) => setErr(e.message));
  useEffect(() => {
    load();
  }, []);

  function open(s?: Source) {
    setEditing(s?.id ?? null);
    setForm(s ? toForm(s) : EMPTY);
    setErr("");
    dialog.current?.showModal();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const config: Record<string, unknown> = { include_keywords: splitWords(form.include), exclude_keywords: splitWords(form.exclude) };
    if (form.kind === "telegram") config.channel = form.target.trim();
    else if (form.kind === "imap") Object.assign(config, { senders: splitWords(form.senders), days: form.days });
    else config.url = form.target.trim();
    const body = JSON.stringify({ name: form.name, kind: form.kind, config, enabled: true });
    try {
      await api(editing ? `/api/sources/${editing}` : "/api/sources", { method: editing ? "PUT" : "POST", body });
      dialog.current?.close();
      load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function run(s: Source) {
    setRunning(s.id);
    try {
      await api(`/api/sources/${s.id}/run`, { method: "POST" });
    } catch (e) {
      setErr((e as Error).message);
    }
    setRunning(null);
    load();
  }

  async function toggle(s: Source) {
    await api(`/api/sources/${s.id}`, { method: "PUT", body: JSON.stringify({ name: s.name, kind: s.kind, config: s.config, enabled: !s.enabled }) });
    load();
  }

  async function remove(s: Source) {
    if (!confirm(`حذف المصدر «${s.name}»؟ الوظائف التي جمعها تبقى.`)) return;
    await api(`/api/sources/${s.id}`, { method: "DELETE" });
    load();
  }

  const hint = KINDS.find((k) => k.kind === form.kind)!.hint;
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: k === "days" ? Number(e.target.value) : e.target.value });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>المصادر</h1>
          <p>من أين تُجمع الوظائف. تُجمع تلقائياً كل ساعة، ويمكنك تشغيل أي مصدر الآن.</p>
        </div>
        <button className="primary" onClick={() => open()}>إضافة مصدر</button>
      </div>

      {err && !dialog.current?.open && <p className="notice error">{err}</p>}

      {!sources ? (
        !err && <p className="muted">جارٍ التحميل...</p>
      ) : !sources.length ? (
        <div className="panel empty">
          <h2>لا توجد مصادر</h2>
          <p>ابدأ بقناة تيليجرام تتابعها، أو فعّل تنبيهات لينكدإن على بريدك وأضفها هنا.</p>
          <button className="primary" onClick={() => open()}>إضافة مصدر</button>
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="list">
            <thead>
              <tr><th>المصدر</th><th>النوع</th><th>آخر جمع</th><th>الوظائف</th><th></th></tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id} style={{ opacity: s.enabled ? 1 : 0.55 }}>
                  <td>
                    <strong>{s.name}</strong>
                    <div className="small muted ltr">{String(s.config.channel ?? s.config.url ?? (s.config.senders as string[] | undefined)?.join(", ") ?? "")}</div>
                    {s.last_error && <div className="small" style={{ color: "var(--rose)" }}>{s.last_error}</div>}
                  </td>
                  <td>{KIND_LABEL[s.kind]}</td>
                  <td className="small">
                    {s.last_run_at ? <>{timeAgo(s.last_run_at)}<br /><span className="muted">{s.last_new_count} جديدة</span></> : <span className="muted">لم يُشغَّل</span>}
                  </td>
                  <td>{s.job_count}</td>
                  <td>
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      <button onClick={() => run(s)} disabled={running === s.id}>{running === s.id ? "جارٍ الجمع..." : "اجمع"}</button>
                      <button className="ghost" onClick={() => open(s)}>تعديل</button>
                      <button className="ghost" onClick={() => toggle(s)}>{s.enabled ? "إيقاف" : "تفعيل"}</button>
                      <button className="ghost danger" onClick={() => remove(s)}>حذف</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <dialog ref={dialog} aria-labelledby="src-title">
        <form onSubmit={submit} style={{ display: "grid", gap: 14 }}>
          <h2 id="src-title">{editing ? "تعديل المصدر" : "إضافة مصدر"}</h2>
          {err && <p className="notice error">{err}</p>}
          <div className="grid2">
            <label className="field"><span>الاسم</span><input required value={form.name} onChange={set("name")} placeholder="وظائف تقنية الرياض" /></label>
            <label className="field">
              <span>النوع</span>
              <select value={form.kind} onChange={set("kind")}>
                {KINDS.map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}
              </select>
            </label>
          </div>
          <p className="small muted" style={{ margin: 0 }}>{hint}</p>
          {form.kind === "imap" ? (
            <div className="grid2">
              <label className="field"><span>عناوين المرسلين (سطر لكل عنوان)</span><textarea className="ltr" rows={3} value={form.senders} onChange={set("senders")} /></label>
              <label className="field"><span>آخر كم يوم</span><input type="number" min={1} max={30} value={form.days} onChange={set("days")} /></label>
            </div>
          ) : (
            <label className="field">
              <span>{form.kind === "telegram" ? "القناة" : "الرابط"}</span>
              <input className="ltr" required value={form.target} onChange={set("target")} placeholder={form.kind === "telegram" ? "@channel_name" : "https://"} />
            </label>
          )}
          <label className="field">
            <span>اقبل فقط ما يحتوي إحدى الكلمات (اختياري)</span>
            <input value={form.include} onChange={set("include")} placeholder="مطور، مهندس، developer، engineer" />
          </label>
          <label className="field">
            <span>استبعد ما يحتوي (اختياري)</span>
            <input value={form.exclude} onChange={set("exclude")} placeholder="سائق، محاسب، تسويق" />
          </label>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="ghost" onClick={() => dialog.current?.close()}>إلغاء</button>
            <button className="primary">{editing ? "حفظ التعديل" : "أضف المصدر"}</button>
          </div>
        </form>
      </dialog>
    </>
  );
}
