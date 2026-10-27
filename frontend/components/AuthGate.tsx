"use client";

import { createContext, FormEvent, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, UNAUTHORIZED_EVENT } from "@/lib/api";

type AuthState = { required: boolean; logout: () => Promise<void> };
const AuthContext = createContext<AuthState>({ required: false, logout: async () => {} });
export const useAuth = () => useContext(AuthContext);

type Me = { auth_required: boolean; authenticated: boolean };

/** يعرض صفحة الدخول بدل المحتوى متى كانت المنصة منشورة بكلمة مرور ولا توجد جلسة صالحة. */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");

  const check = useCallback(async () => {
    try {
      setMe(await api<Me>("/api/auth/me"));
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    check();
    const onUnauthorized = () => setMe((m) => (m ? { ...m, authenticated: false } : m));
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [check]);

  const logout = useCallback(async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    setMe((m) => (m ? { ...m, authenticated: false } : m));
  }, []);

  if (!me) {
    return (
      <div className="login-wrap">
        {error ? (
          <div className="panel login">
            <p className="notice error" role="alert">{error}</p>
            <button onClick={check}>إعادة المحاولة</button>
          </div>
        ) : (
          <p className="muted">جارٍ التحميل…</p>
        )}
      </div>
    );
  }
  if (me.auth_required && !me.authenticated) return <Login onDone={check} />;
  return <AuthContext.Provider value={{ required: me.auth_required, logout }}>{children}</AuthContext.Provider>;
}

function Login({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) });
      setPassword("");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="panel login" onSubmit={submit}>
        <div className="brand" style={{ padding: 0 }}>
          فرصة
          <small>رادارك الشخصي للوظائف</small>
        </div>
        <label className="field">
          <span>كلمة المرور</span>
          <input type="password" autoComplete="current-password" autoFocus required
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="notice error" role="alert">{error}</p>}
        <button className="primary" disabled={busy || !password}>{busy ? "جارٍ الدخول…" : "دخول"}</button>
      </form>
    </div>
  );
}
