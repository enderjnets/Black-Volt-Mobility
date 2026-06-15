"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Icon } from "../Icon";
import { useI18n } from "@/lib/i18n";

const TABS = [
  { href: "/", icon: "home", key: "nav.home" },
  { href: "/book", icon: "zap", key: "nav.book" },
  { href: "/trips", icon: "navigation", key: "nav.trips" },
  { href: "/your-driver", icon: "user", key: "nav.driver" },
];

/** Mobile bottom tab bar (native-app feel). Hidden on desktop via the
 *  `.bv-tabbar` rule in globals.css. */
export function ClientTabBar() {
  const { t } = useI18n();
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  return (
    <nav
      className="bv-tabbar"
      style={{
        position: "fixed",
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 45,
        gridTemplateColumns: "repeat(4, 1fr)",
        background: "rgba(15,15,21,0.92)",
        backdropFilter: "blur(16px)",
        borderTop: "1px solid var(--line-strong)",
        paddingBottom: "max(6px, env(safe-area-inset-bottom))",
      }}
    >
      {TABS.map((tb) => {
        const active = isActive(tb.href);
        return (
          <Link
            key={tb.href}
            href={tb.href}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 4,
              minHeight: 58,
              padding: "9px 0 7px",
              textDecoration: "none",
              color: active ? "var(--volt)" : "var(--silver)",
              WebkitTapHighlightColor: "transparent",
            }}
          >
            <Icon name={tb.icon} size={22} color="currentColor" fill={tb.icon === "zap" && active ? "currentColor" : "none"} />
            <span style={{ fontFamily: "var(--font-sans)", fontSize: 11, fontWeight: active ? 700 : 500 }}>{t(tb.key)}</span>
          </Link>
        );
      })}
    </nav>
  );
}
