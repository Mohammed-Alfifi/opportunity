"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "./AuthGate";

const LINKS = [
  { href: "/", label: "الفرص" },
  { href: "/applications", label: "التقديمات" },
  { href: "/sources", label: "المصادر" },
  { href: "/profile", label: "ملفي" },
];

export default function Nav() {
  const path = usePathname();
  const { required, logout } = useAuth();
  return (
    <nav className="nav" aria-label="القائمة الرئيسية">
      <div className="brand">
        فرصة
        <small>رادارك الشخصي للوظائف</small>
      </div>
      {LINKS.map((l) => {
        const active = l.href === "/" ? path === "/" || path.startsWith("/jobs") : path.startsWith(l.href);
        return (
          <Link key={l.href} href={l.href} className={active ? "active" : ""} aria-current={active ? "page" : undefined}>
            {l.label}
          </Link>
        );
      })}
      <div className="foot">
        {required ? (
          <button className="ghost" onClick={logout} style={{ padding: 0 }}>تسجيل الخروج</button>
        ) : (
          "بياناتك محفوظة على جهازك فقط."
        )}
      </div>
    </nav>
  );
}
