// في الإنتاج الواجهة والخلفية على نفس الأصل، فالمسار النسبي يكفي
export const API = process.env.NEXT_PUBLIC_API_URL ?? "";
export const UNAUTHORIZED_EVENT = "forsa:unauthorized";

export type Job = {
  id: number;
  source_id: number | null;
  source_name: string | null;
  title: string;
  company: string | null;
  location: string | null;
  url: string | null;
  posted_at: string | null;
  lang: "ar" | "en";
  contact_email: string | null;
  status: "new" | "shortlisted" | "applied" | "ignored";
  score: number | null;
  created_at: string;
};

export type Analysis = {
  engine: "heuristic" | "llm";
  score: number;
  recommendation: string;
  summary: string;
  matched_skills?: string[];
  missing_skills?: string[];
  strengths?: string[];
  concerns?: string[];
  tips?: string[];
  llm_error?: string;
};

export type JobDetail = Job & { description: string; analysis: Analysis | null };

export type Source = {
  id: number;
  name: string;
  kind: "rss" | "telegram" | "webpage" | "imap";
  config: Record<string, unknown>;
  enabled: boolean;
  last_run_at: string | null;
  last_error: string | null;
  last_new_count: number;
  job_count: number;
};

export type Application = {
  id: number;
  job_id: number;
  to_email: string;
  subject: string;
  body: string;
  attach_cv: boolean;
  status: "draft" | "sent" | "failed";
  error: string | null;
  sent_at: string | null;
  updated_at: string;
  job_title?: string | null;
  job_company?: string | null;
};

export type Profile = {
  full_name: string;
  email: string;
  phone: string;
  headline: string;
  summary: string;
  skills: string[];
  target_titles: string[];
  locations: string[];
  years_experience: number;
  links: string[];
  cv_text: string;
  cv_filename: string | null;
  min_score_to_notify: number;
};

export type Status = {
  llm: { enabled: boolean; provider: string; model: string };
  smtp: { configured: boolean; user: string; transport?: "smtp" | "gas" };
  imap: { configured: boolean };
  cv_uploaded: boolean;
  collect_interval_minutes: number | null;
};

export class ApiError extends Error {}

/** يعرض الروابط القادمة من الإعلانات فقط إن كانت http/https. */
export function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      ...init,
      headers: {
        "X-Forsa-Client": "web",
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
      cache: "no-store",
      credentials: "include",
    });
  } catch {
    throw new ApiError(API ? `الخادم لا يستجيب على ${API}. شغّل الخلفية ثم أعد المحاولة.` : "تعذّر الاتصال بالخادم. إن كانت الخدمة نائمة فانتظر دقيقة ثم أعد المحاولة.");
  }
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    throw new ApiError(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => String(x.msg).replace(/^Value error, /, "")).join("، ") : `خطأ ${res.status}`);
  }
  return data as T;
}

export const STATUS_LABEL: Record<Job["status"], string> = {
  new: "جديدة",
  shortlisted: "مرشحة",
  applied: "تم التقديم",
  ignored: "متجاهلة",
};

export function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 3600) return `قبل ${Math.max(1, Math.round(diff / 60))} دقيقة`;
  if (diff < 86400) return `قبل ${Math.round(diff / 3600)} ساعة`;
  const days = Math.round(diff / 86400);
  return days === 1 ? "أمس" : `قبل ${days} يوم`;
}
