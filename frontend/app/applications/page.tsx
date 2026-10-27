"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Application, timeAgo } from "@/lib/api";

const LABEL = { draft: "مسودة", sent: "مرسل", failed: "فشل الإرسال" } as const;
const CHIP = { draft: "chip", sent: "chip good", failed: "chip warn" } as const;

export default function ApplicationsPage() {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api<Application[]>("/api/applications").then(setApps).catch((e) => setErr(e.message));
  }, []);

  const sent = apps?.filter((a) => a.status === "sent").length ?? 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>التقديمات</h1>
          <p>{apps ? `${sent} تقديم مرسل، و${apps.length - sent} مسودة` : " "}</p>
        </div>
      </div>
      {err && <p className="notice error">{err}</p>}
      {apps && !apps.length ? (
        <div className="panel empty">
          <h2>لا توجد تقديمات</h2>
          <p>افتح أي فرصة واضغط «جهّز الرسالة» لتبدأ.</p>
          <Link href="/">عرض الفرص</Link>
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="list">
            <thead>
              <tr><th>الوظيفة</th><th>إلى</th><th>الحالة</th><th>آخر تحديث</th></tr>
            </thead>
            <tbody>
              {apps?.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link href={`/jobs?id=${a.job_id}`} dir="auto">{a.job_title}</Link>
                    {a.job_company && <div className="small muted" dir="auto">{a.job_company}</div>}
                  </td>
                  <td className="ltr small">{a.to_email || "—"}</td>
                  <td>
                    <span className={CHIP[a.status]}>{LABEL[a.status]}</span>
                    {a.status === "failed" && a.error && <div className="small" style={{ color: "var(--rose)" }}>{a.error}</div>}
                  </td>
                  <td className="small">{timeAgo(a.sent_at || a.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
