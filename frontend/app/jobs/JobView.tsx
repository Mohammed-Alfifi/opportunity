"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ScoreRing from "@/components/ScoreRing";
import { api, Application, Job, JobDetail, safeHref, STATUS_LABEL, Status, timeAgo } from "@/lib/api";

export default function JobView() {
  const raw = useSearchParams().get("id") ?? "";
  const id = /^\d+$/.test(raw) ? raw : "0";
  const [job, setJob] = useState<JobDetail | null>(null);
  const [app, setApp] = useState<Application | null>(null);
  const [status, setStatusInfo] = useState<Status | null>(null);
  const [busy, setBusy] = useState<string>("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error" | ""; text: string } | null>(null);
  const [lang, setLang] = useState<"ar" | "en">("ar");
  const [instructions, setInstructions] = useState("");

  const load = useCallback(async () => {
    try {
      const [j, a, s] = await Promise.all([
        api<JobDetail>(`/api/jobs/${id}`),
        api<Application | null>(`/api/jobs/${id}/application`),
        api<Status>("/api/status"),
      ]);
      setJob(j);
      setApp(a);
      setStatusInfo(s);
      setLang(j.lang);
    } catch (e) {
      setMsg({ kind: "error", text: (e as Error).message });
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function run<T>(key: string, fn: () => Promise<T>, ok?: string) {
    setBusy(key);
    setMsg(null);
    try {
      const r = await fn();
      if (ok) setMsg({ kind: "ok", text: ok });
      return r;
    } catch (e) {
      setMsg({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  }

  const analyze = (useLlm: boolean) =>
    run("analyze", async () => setJob(await api<JobDetail>(`/api/jobs/${id}/analyze?use_llm=${useLlm}`, { method: "POST" })));

  const setJobStatus = (s: Job["status"]) =>
    run("status", async () => setJob(await api<JobDetail>(`/api/jobs/${id}`, { method: "PATCH", body: JSON.stringify({ status: s }) })));

  const draft = () =>
    run("draft", async () => {
      const a = await api<Application>(`/api/jobs/${id}/application`, {
        method: "POST",
        body: JSON.stringify({ lang, instructions, use_llm: true }),
      });
      setApp(a);
      if (a.error) setMsg({ kind: "", text: `استُخدم القالب الجاهز لأن النموذج لم يستجب: ${a.error}` });
    });

  const save = async (silent = false) => {
    if (!app) return;
    const a = await api<Application>(`/api/applications/${app.id}`, {
      method: "PATCH",
      body: JSON.stringify({ to_email: app.to_email, subject: app.subject, body: app.body, attach_cv: app.attach_cv }),
    });
    setApp(a);
    if (!silent) setMsg({ kind: "ok", text: "حُفظت المسودة." });
  };

  const send = () => {
    if (!app) return;
    if (!confirm(`إرسال التقديم إلى ${app.to_email}؟ لا يمكن التراجع بعد الإرسال.`)) return;
    run(
      "send",
      async () => {
        await save(true);
        setApp(await api<Application>(`/api/applications/${app.id}/send`, { method: "POST" }));
        setJob(await api<JobDetail>(`/api/jobs/${id}`));
      },
      "أُرسل التقديم. تجده في صفحة التقديمات."
    );
  };

  if (!job) return msg ? <p className="notice error">{msg.text}</p> : <p className="muted">جارٍ التحميل...</p>;

  const a = job.analysis;
  const sent = app?.status === "sent";

  return (
    <>
      <p className="small"><Link href="/">الفرص</Link></p>
      <div className="page-head">
        <div>
          <h1 dir="auto">{job.title}</h1>
          <p>
            {[job.company, job.location, job.source_name, timeAgo(job.posted_at || job.created_at)].filter(Boolean).join("، ")}
            {" "}<span className="chip">{STATUS_LABEL[job.status]}</span>
          </p>
        </div>
        <div className="row">
          {safeHref(job.url) && <a className="btn" href={safeHref(job.url)} target="_blank" rel="noopener noreferrer">فتح الإعلان الأصلي</a>}
          {job.status !== "shortlisted" && job.status !== "applied" && <button onClick={() => setJobStatus("shortlisted")}>رشّحها</button>}
          {job.status !== "ignored" && job.status !== "applied" && <button className="ghost" onClick={() => setJobStatus("ignored")}>تجاهل</button>}
          {job.status !== "applied" && <button className="ghost" onClick={() => setJobStatus("applied")} title="إذا قدّمت من موقع الجهة مباشرة">قدّمت عليها</button>}
        </div>
      </div>

      {msg && msg.text && <p className={`notice ${msg.kind}`} role="status">{msg.text}</p>}

      <div className="detail">
        <section className="panel">
          <h2 style={{ marginBottom: 12 }}>نص الإعلان</h2>
          <div className="desc" dir="auto">{job.description || "لا يوجد وصف. افتح الإعلان الأصلي."}</div>
        </section>

        <aside className="side">
          <section className="panel">
            <div className="verdict">
              <ScoreRing score={job.score} size={84} />
              <div>
                <strong>{a?.recommendation ?? "لم تُحلَّل"}</strong>
                <span className="small muted">
                  {a?.engine === "llm" ? "تحليل بالنموذج اللغوي" : "تقييم سريع بمطابقة المهارات"}
                </span>
              </div>
            </div>
            {a?.summary && <p>{a.summary}</p>}
            {!!a?.strengths?.length && (
              <>
                <h3 className="small">نقاط القوة</h3>
                <ul className="points">{a.strengths.map((s) => <li key={s}>{s}</li>)}</ul>
              </>
            )}
            {!!a?.concerns?.length && (
              <>
                <h3 className="small" style={{ marginTop: 10 }}>ما يجب الانتباه له</h3>
                <ul className="points">{a.concerns.map((s) => <li key={s}>{s}</li>)}</ul>
              </>
            )}
            {!!a?.tips?.length && (
              <>
                <h3 className="small" style={{ marginTop: 10 }}>نصائح للتقديم</h3>
                <ul className="points">{a.tips.map((s) => <li key={s}>{s}</li>)}</ul>
              </>
            )}
            {a?.llm_error && <p className="notice small">{a.llm_error}</p>}
            <div className="row" style={{ marginTop: 14 }}>
              {status?.llm.enabled ? (
                <button onClick={() => analyze(true)} disabled={!!busy}>{busy === "analyze" ? "جارٍ التحليل..." : "حلّل بعمق"}</button>
              ) : (
                <span className="small muted">للتحليل العميق اضبط مزود النموذج في ملف <bdi className="ltr-code">.env</bdi></span>
              )}
            </div>
          </section>

          <section className="panel" aria-labelledby="apply-h">
            <h2 id="apply-h" style={{ marginBottom: 12 }}>رسالة التقديم</h2>
            {sent ? (
              <p className="notice ok">أُرسلت إلى {app!.to_email} {timeAgo(app!.sent_at)}.</p>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                <div className="grid2">
                  <label className="field">
                    <span>لغة الرسالة</span>
                    <select value={lang} onChange={(e) => setLang(e.target.value as "ar" | "en")}>
                      <option value="ar">العربية</option>
                      <option value="en">English</option>
                    </select>
                  </label>
                  <div style={{ alignSelf: "end" }}>
                    <button className={app ? "" : "primary"} style={{ width: "100%" }} onClick={draft} disabled={!!busy}>
                      {busy === "draft" ? "جارٍ الكتابة..." : app ? "أعد الكتابة" : "جهّز الرسالة"}
                    </button>
                  </div>
                </div>
                {status?.llm.enabled && (
                  <label className="field">
                    <span>توجيه إضافي (اختياري)</span>
                    <input value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="مثال: ركّز على مشروع تحليل الكاميرات" />
                  </label>
                )}
              </div>
            )}

            {app && !sent && (
              <div style={{ display: "grid", gap: 10, marginTop: 14 }}>
                <label className="field">
                  <span>إلى</span>
                  <input className="ltr" type="email" value={app.to_email} onChange={(e) => setApp({ ...app, to_email: e.target.value })} placeholder="hr@company.sa" />
                  {!app.to_email && "الإعلان لا يذكر بريداً. أضفه من نص الإعلان أو قدّم من الرابط الأصلي."}
                </label>
                <label className="field">
                  <span>الموضوع</span>
                  <input dir="auto" value={app.subject} onChange={(e) => setApp({ ...app, subject: e.target.value })} />
                </label>
                <label className="field">
                  <span>النص</span>
                  <textarea dir="auto" rows={14} value={app.body} onChange={(e) => setApp({ ...app, body: e.target.value })} />
                </label>
                <label className="row small">
                  <input type="checkbox" style={{ width: "auto" }} checked={app.attach_cv} onChange={(e) => setApp({ ...app, attach_cv: e.target.checked })} />
                  إرفاق سيرتي الذاتية {status && !status.cv_uploaded && <Link href="/profile">(لم تُرفع بعد)</Link>}
                </label>
                {app.status === "failed" && app.error && <p className="notice error">{app.error}</p>}
                {status && !status.smtp.configured && <p className="notice small">الإرسال غير مضبوط بعد: محلياً اضبط <bdi className="ltr-code">SMTP_USER</bdi> و<bdi className="ltr-code">SMTP_PASSWORD</bdi>، وعلى الاستضافة اضبط <bdi className="ltr-code">GAS_URL</bdi> و<bdi className="ltr-code">GAS_TOKEN</bdi></p>}
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  <button onClick={() => save()} disabled={!!busy}>حفظ المسودة</button>
                  <button className="primary" onClick={send} disabled={!!busy || !app.to_email || !status?.smtp.configured}>
                    {busy === "send" ? "جارٍ الإرسال..." : "أرسل التقديم"}
                  </button>
                </div>
              </div>
            )}
          </section>
        </aside>
      </div>
    </>
  );
}
