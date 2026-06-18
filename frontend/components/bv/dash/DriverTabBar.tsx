"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { useI18n } from "@/lib/i18n";
import { fetchMe, logout, type Me } from "@/lib/auth";

const PRIMARY = [
  { seg: "overview", href: "/dashboard", icon: "layout-dashboard", key: "dash.nav.overview" },
  { seg: "rides", href: "/dashboard/rides", icon: "navigation", key: "dash.nav.rides" },
  { seg: "clients", href: "/dashboard/clients", icon: "users", key: "dash.nav.clients" },
  { seg: "inbox", href: "/dashboard/inbox", icon: "message-circle", key: "dash.nav.inbox" },
];
const MORE = [
  { seg: "stats", href: "/dashboard/stats", icon: "bar-chart-3", key: "dash.nav.stats" },
  { seg: "social", href: "/dashboard/social", icon: "share-2", key: "dash.nav.social" },
  { seg: "add", href: "/dashboard/add", icon: "plus", key: "dash.nav.book" },
  { seg: "analytics", href: "/dashboard/analytics", icon: "trending-up", key: "dash.nav.insights" },
  { seg: "rates", href: "/dashboard/rates", icon: "dollar-sign", key: "dash.nav.rates" },
  { seg: "settings", href: "/dashboard/settings", icon: "settings", key: "dash.nav.settings" },
];
const ADMIN_ITEM = { seg: "team", href: "/dashboard/team", icon: "shield-check", key: "dash.nav.team" };

function segOf(pathname: string) {
  return pathname.split("/").filter(Boolean)[1] ?? "overview";
}

export function DriverTabBar() {
  const { t } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const seg = segOf(pathname);
  const [moreOpen, setMoreOpen] = useState(false);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    let alive = true;
    fetchMe().then((m) => alive && setMe(m)).catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const moreActive = (me?.is_admin ? [...MORE, ADMIN_ITEM] : MORE).some((m) => m.seg === seg);
  const identity = me?.email ? me.email.split("@")[0] : me?.is_admin ? "Owner" : "Driver";
  const roleLabel = t(me?.is_admin ? "dash.role.admin" : "dash.role.driver");

  const tab = (active: boolean): React.CSSProperties => ({
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    minHeight: 58,
    padding: "9px 0 7px",
    border: "none",
    background: "none",
    cursor: "pointer",
    textDecoration: "none",
    color: active ? "var(--volt)" : "var(--silver)",
    WebkitTapHighlightColor: "transparent",
    fontFamily: "var(--font-sans)",
  });

  return (
    <>
      <nav
        className="bv-tabbar"
        style={{
          position: "fixed",
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 45,
          gridTemplateColumns: "repeat(5, 1fr)",
          background: "rgba(15,15,21,0.92)",
          backdropFilter: "blur(16px)",
          borderTop: "1px solid var(--line-strong)",
          paddingBottom: "max(6px, env(safe-area-inset-bottom))",
        }}
      >
        {PRIMARY.map((tb) => {
          const active = seg === tb.seg;
          return (
            <Link key={tb.seg} href={tb.href} style={tab(active)}>
              <Icon name={tb.icon} size={22} color="currentColor" />
              <span style={{ fontSize: 11, fontWeight: active ? 700 : 500 }}>{t(tb.key)}</span>
            </Link>
          );
        })}
        <button onClick={() => setMoreOpen(true)} style={tab(moreActive)}>
          <Icon name="more-horizontal" size={22} color="currentColor" />
          <span style={{ fontSize: 11, fontWeight: moreActive ? 700 : 500 }}>{t("dash.nav.more")}</span>
        </button>
      </nav>

      {moreOpen && (
        <div
          onClick={() => setMoreOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 60,
            background: "rgba(5,5,9,0.6)",
            backdropFilter: "blur(3px)",
            display: "flex",
            alignItems: "flex-end",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "100%",
              background: "var(--obsidian)",
              borderTop: "1px solid var(--volt-border)",
              borderTopLeftRadius: 18,
              borderTopRightRadius: 18,
              padding: "10px 16px calc(20px + env(safe-area-inset-bottom))",
              boxShadow: "var(--shadow-pop)",
            }}
          >
            <div style={{ width: 38, height: 4, borderRadius: 99, background: "var(--line-strong)", margin: "0 auto 14px" }} />
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {me?.is_admin && (
                <>
                  <Link
                    href={ADMIN_ITEM.href}
                    onClick={() => setMoreOpen(false)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 13,
                      padding: "14px 12px",
                      borderRadius: "var(--radius-md)",
                      textDecoration: "none",
                      fontFamily: "var(--font-sans)",
                      fontSize: 15,
                      fontWeight: 700,
                      background: "var(--volt-bg)",
                      color: "var(--volt)",
                      boxShadow: "inset 0 0 0 1px var(--volt-border)",
                    }}
                  >
                    <Icon name={ADMIN_ITEM.icon} size={20} color="currentColor" />
                    {t(ADMIN_ITEM.key)}
                    <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--volt)", textTransform: "uppercase" }}>
                      {t("dash.role.admin")}
                    </span>
                  </Link>
                  <div style={{ height: 1, background: "var(--line)", margin: "6px 2px" }} />
                </>
              )}
              {MORE.map((it) => {
                const active = seg === it.seg;
                return (
                  <Link
                    key={it.seg}
                    href={it.href}
                    onClick={() => setMoreOpen(false)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 13,
                      padding: "14px 12px",
                      borderRadius: "var(--radius-md)",
                      textDecoration: "none",
                      fontFamily: "var(--font-sans)",
                      fontSize: 15,
                      fontWeight: active ? 700 : 500,
                      background: active ? "var(--volt-bg)" : "transparent",
                      color: active ? "var(--volt)" : "var(--arctic)",
                      boxShadow: active ? "inset 0 0 0 1px var(--volt-border)" : "none",
                    }}
                  >
                    <Icon name={it.icon} size={20} color="currentColor" />
                    {t(it.key)}
                  </Link>
                );
              })}
            </div>
            <div style={{ height: 1, background: "var(--line)", margin: "12px 0" }} />
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "6px 12px 4px" }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  border: "1.5px solid var(--volt)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: "var(--obsidian-3)",
                  flexShrink: 0,
                }}
              >
                <Icon name="user" size={19} color="var(--silver)" />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{identity}</div>
                <div style={{ fontSize: 12, color: "var(--fg3)" }}>{roleLabel}</div>
              </div>
              <button
                onClick={async () => {
                  await logout();
                  router.push("/login");
                }}
                aria-label={t("auth.signout")}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 8, display: "flex" }}
              >
                <Icon name="log-out" size={18} color="var(--fg3)" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
