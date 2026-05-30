"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useState } from "react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { LanguageSwitcher } from "../../ui/LanguageSwitcher";
import { useI18n } from "@/lib/i18n";

export function StatusPill({ status }: { status: "upcoming" | "active" | "done" }) {
  const { t } = useI18n();
  const tone = status === "active" ? "warning" : status === "done" ? "success" : "volt";
  const colors: Record<string, [string, string, string]> = {
    volt: ["var(--volt)", "var(--volt-border)", "var(--volt-bg)"],
    warning: ["var(--warning)", "rgba(255,194,75,0.4)", "rgba(255,194,75,0.12)"],
    success: ["var(--success)", "rgba(43,212,160,0.4)", "rgba(43,212,160,0.12)"],
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
  { seg: "inbox", href: "/dashboard/inbox", icon: "message-circle", key: "dash.nav.inbox" },
  { seg: "rates", href: "/dashboard/rates", icon: "dollar-sign", key: "dash.nav.rates" },
  { seg: "settings", href: "/dashboard/settings", icon: "settings", key: "dash.nav.settings" },
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
          {NAV.map((n) => (
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
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>Ender</div>
            <div style={{ fontSize: 11, color: "var(--fg3)" }}>{t("dash.owner")}</div>
          </div>
          <Icon name="log-out" size={16} color="var(--fg3)" />
        </div>
      </aside>

      <div style={{ flex: 1, minWidth: 0 }}>
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
            <div style={{ position: "relative" }}>
              <Icon name="bell" size={19} color="var(--silver)" />
              <span
                style={{
                  position: "absolute",
                  top: -2,
                  right: -2,
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: "var(--volt)",
                  boxShadow: "var(--shadow-volt-sm)",
                }}
              />
            </div>
            <Button variant="solid" size="sm" icon="plus" onClick={() => router.push("/dashboard/add")}>
              {t("dash.newRide")}
            </Button>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}
