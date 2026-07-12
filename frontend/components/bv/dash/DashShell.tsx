"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { LanguageSwitcher } from "../../ui/LanguageSwitcher";
import { useI18n } from "@/lib/i18n";
import { fetchMe, logout, type Me } from "@/lib/auth";
import { InstallHint } from "../InstallHint";
import { DriverTabBar } from "./DriverTabBar";
import { NotificationsBell } from "./NotificationsBell";

export function StatusPill({
  status,
}: {
  status: "upcoming" | "active" | "done" | "cancelled" | "overdue";
}) {
  const { t } = useI18n();
  const tone =
    status === "overdue"
      ? "overdue"
      : status === "active"
        ? "warning"
        : status === "done"
          ? "success"
          : status === "cancelled"
            ? "danger"
            : "volt";
  const colors: Record<string, [string, string, string]> = {
    volt: ["var(--volt)", "var(--volt-border)", "var(--volt-bg)"],
    warning: ["var(--warning)", "rgba(255,194,75,0.4)", "rgba(255,194,75,0.12)"],
    success: ["var(--success)", "rgba(43,212,160,0.4)", "rgba(43,212,160,0.12)"],
    danger: ["var(--danger)", "rgba(255,92,110,0.4)", "rgba(255,92,110,0.12)"],
    overdue: ["#FF8A3D", "rgba(255,138,61,0.45)", "rgba(255,138,61,0.14)"],
  };
  const c = colors[tone];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 12,
        fontWeight: 600,
        fontFamily: "var(--font-sans)",
        color: c[0],
        background: c[2],
        border: `1px solid ${c[1]}`,
        borderRadius: "var(--radius-full)",
        padding: "3px 10px",
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: c[0] }} />
      {t(`dash.status.${status}`)}
    </span>
  );
}

const NAV: { seg: string; href: string; icon: string; key: string }[] = [
  { seg: "overview", href: "/dashboard", icon: "layout-dashboard", key: "dash.nav.overview" },
  { seg: "add", href: "/dashboard/add", icon: "plus", key: "dash.nav.book" },
  { seg: "rides", href: "/dashboard/rides", icon: "navigation", key: "dash.nav.rides" },
  { seg: "clients", href: "/dashboard/clients", icon: "users", key: "dash.nav.clients" },
  { seg: "stats", href: "/dashboard/stats", icon: "bar-chart-3", key: "dash.nav.stats" },
  { seg: "inbox", href: "/dashboard/inbox", icon: "message-circle", key: "dash.nav.inbox" },
  { seg: "analytics", href: "/dashboard/analytics", icon: "trending-up", key: "dash.nav.insights" },
  { seg: "rates", href: "/dashboard/rates", icon: "dollar-sign", key: "dash.nav.rates" },
  { seg: "discounts", href: "/dashboard/discounts", icon: "tag", key: "dash.nav.discounts" },
  { seg: "settings", href: "/dashboard/settings", icon: "settings", key: "dash.nav.settings" },
];

// Super-admin only (social management + the access list). Appended to the nav
// when me.is_admin — regular drivers never see these.
const ADMIN_NAV = [
  { seg: "events", href: "/dashboard/events", icon: "calendar", key: "dash.nav.events" },
  { seg: "blog", href: "/dashboard/blog", icon: "pencil", key: "dash.nav.blog" },
  { seg: "reviews", href: "/dashboard/reviews", icon: "star", key: "dash.nav.reviews" },
  { seg: "social", href: "/dashboard/social", icon: "share-2", key: "dash.nav.social" },
  { seg: "team", href: "/dashboard/team", icon: "shield-check", key: "dash.nav.team" },
];

function SideLink({ href, icon, label, active }: { href: string; icon: string; label: string; active: boolean }) {
  const [h, setH] = useState(false);
  return (
    <Link
      href={href}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 11,
        padding: "10px 12px",
        borderRadius: "var(--radius-md)",
        textDecoration: "none",
        fontFamily: "var(--font-sans)",
        fontSize: 14,
        fontWeight: active ? 600 : 500,
        background: active ? "var(--volt-bg)" : h ? "var(--obsidian-2)" : "transparent",
        color: active ? "var(--volt)" : h ? "var(--arctic)" : "var(--silver)",
        boxShadow: active ? "inset 0 0 0 1px var(--volt-border)" : "none",
        transition: "all .14s",
      }}
    >
      <Icon name={icon} size={18} color="currentColor" />
      <span className="bv-dash-text">{label}</span>
    </Link>
  );
}

function segOf(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean); // ["dashboard", "rides"?]
  return parts[1] ?? "overview";
}

export function DashShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const seg = segOf(pathname);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    let alive = true;
    fetchMe().then((m) => alive && setMe(m)).catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const nav = me?.is_admin ? [...NAV, ...ADMIN_NAV] : NAV;
  const identity = me?.email ? me.email.split("@")[0] : me?.is_admin ? "Owner" : "Driver";
  const roleLabel = t(me?.is_admin ? "dash.role.admin" : "dash.role.driver");

  return (
    <div style={{ display: "flex", minHeight: "100dvh", background: "var(--void)" }}>
      <aside
        className="bv-dash-aside"
        style={{
          width: 232,
          flexShrink: 0,
          background: "var(--obsidian)",
          borderRight: "1px solid var(--line)",
          display: "flex",
          flexDirection: "column",
          padding: "20px 14px",
          height: "100dvh",
          position: "sticky",
          top: 0,
        }}
      >
        <div style={{ padding: "4px 8px 22px" }}>
          <Link href="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: 9 }}>
            <Icon name="zap" size={19} color="#00E5FF" fill="#00E5FF" />
            <span
              className="bv-dash-text"
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 700,
                fontSize: 16,
                letterSpacing: "0.04em",
                color: "var(--arctic)",
                textTransform: "uppercase",
                whiteSpace: "nowrap",
              }}
            >
              Black Volt <span style={{ color: "var(--volt)" }}>Mobility</span>
            </span>
          </Link>
        </div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 3, flex: 1 }}>
          {nav.map((n) => (
            <SideLink key={n.seg} href={n.href} icon={n.icon} label={t(n.key)} active={seg === n.seg} />
          ))}
        </nav>
        <div
          style={{
            marginTop: 12,
            padding: 12,
            borderRadius: "var(--radius-md)",
            background: "var(--obsidian-2)",
            border: "1px solid var(--line)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: "50%",
              border: "1.5px solid var(--volt)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--obsidian-3)",
              flexShrink: 0,
            }}
          >
            <Icon name="user" size={17} color="var(--silver)" />
          </div>
          <div className="bv-dash-text" style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{identity}</div>
            <div style={{ fontSize: 11, color: "var(--fg3)" }}>{roleLabel}</div>
          </div>
          <button
            onClick={async () => {
              await logout();
              router.push("/login");
            }}
            aria-label={t("auth.signout")}
            title={t("auth.signout")}
            style={{ background: "none", border: "none", cursor: "pointer", padding: 2, display: "flex" }}
          >
            <Icon name="log-out" size={16} color="var(--fg3)" />
          </button>
        </div>
      </aside>

      <div className="bv-mobile-pad" style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "18px 28px",
            borderBottom: "1px solid var(--line)",
            position: "sticky",
            top: 0,
            zIndex: 10,
            background: "rgba(10,10,15,0.82)",
            backdropFilter: "blur(12px)",
            gap: 12,
          }}
        >
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--arctic)", margin: 0 }}>
            {t(`dash.title.${seg}`)}
          </h1>
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <LanguageSwitcher />
            <NotificationsBell />
            <Button variant="solid" size="sm" icon="plus" onClick={() => router.push("/dashboard/add")}>
              {t("dash.newRide")}
            </Button>
          </div>
        </div>
        {children}
      </div>
      <DriverTabBar />
      <InstallHint />
    </div>
  );
}
