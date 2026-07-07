"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { Icon } from "../Icon";
import { InstallButton } from "../InstallButton";
import { InstallHint } from "../InstallHint";
import { Button, Logo } from "../ui";
import { VersionButton } from "../../ui/VersionButton";
import { LanguageSwitcher } from "../../ui/LanguageSwitcher";
import { useI18n } from "@/lib/i18n";
import { fetchMe, logout } from "@/lib/auth";
import { track } from "@/lib/analytics";
// Joules chat: code-split out of the shared first-load bundle — the module (panel
// + streaming + history) loads on the client after hydration, not on the critical
// path. Its floating launcher appears a beat after paint; nothing else depends on it.
const ChatAssistant = dynamic(() => import("./Chat").then((m) => m.ChatAssistant), {
  ssr: false,
});
import { ClientTabBar } from "./ClientTabBar";
import { SEO_ROUTES } from "@/lib/seoRoutes";
import { ProfileGate } from "./ProfileGate";
import { AgreementGate } from "../AgreementGate";
import { BV_USER, type BvUser, SignInModal } from "./SignInModal";

interface WebCtx {
  user: BvUser | null;
  openChat: () => void;
  // Optional `onDone` resumes the caller's flow after sign-in (e.g. the booking
  // wall) instead of the default redirect to /account.
  openSignIn: (onDone?: () => void) => void;
  signOut: () => void;
}
const Ctx = createContext<WebCtx | null>(null);
export function useWeb(): WebCtx {
  return (
    useContext(Ctx) ?? { user: null, openChat: () => {}, openSignIn: () => {}, signOut: () => {} }
  );
}

const NAV = [
  { href: "/", key: "nav.home" },
  { href: "/book", key: "nav.book" },
  { href: "/rides", key: "nav.rides" },
  { href: "/blog", key: "nav.blog" },
  { href: "/trips", key: "nav.trips" },
  // Smart route: resolves to the visitor's designated driver (see /your-driver).
  { href: "/your-driver", key: "nav.driver" },
];

function MenuItem({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  const [h, setH] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 11,
        width: "100%",
        textAlign: "left",
        padding: "11px 14px",
        border: "none",
        cursor: "pointer",
        background: h ? "var(--obsidian-3)" : "transparent",
        color: h ? "var(--arctic)" : "var(--silver)",
        fontSize: 13.5,
        fontFamily: "var(--font-sans)",
        fontWeight: 500,
      }}
    >
      <Icon name={icon} size={16} color="currentColor" />
      {label}
    </button>
  );
}

export function WebShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<BvUser | null>(null);
  const [signin, setSignin] = useState(false);
  const [afterSignIn, setAfterSignIn] = useState<(() => void) | null>(null);
  const [gateNext, setGateNext] = useState<(() => void) | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const [pendingAgreements, setPendingAgreements] = useState<string[]>([]);

  const openSignIn = (onDone?: () => void) => {
    setAfterSignIn(() => onDone ?? null);
    setSignin(true);
  };

  // Reflect an existing passenger session (real Google sign-in) on load, and
  // surface any mandatory agreements the passenger still has to sign.
  const refreshMe = () => {
    fetchMe().then((me) => {
      if (me.authenticated && me.role === "passenger") {
        const email = me.email || "";
        setUser({ name: email ? email.split("@")[0] : "Passenger", email, since: "" });
        setPendingAgreements(me.agreements_pending ?? []);
      } else {
        setPendingAgreements([]);
      }
    });
  };
  useEffect(() => {
    refreshMe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ctx: WebCtx = {
    user,
    openChat: () => setChatOpen(true),
    openSignIn,
    signOut: async () => {
      await logout();
      setUser(null);
      router.push("/");
    },
  };

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  // The mandatory agreement gate fully REPLACES the app (the booking UI is never
  // mounted behind it) — matches AuthGuard semantics so it can't be bypassed in
  // the DOM and the live form isn't reachable by keyboard/programmatic access.
  if (pendingAgreements.length > 0) {
    return <AgreementGate pending={pendingAgreements} onComplete={refreshMe} />;
  }

  return (
    <Ctx.Provider value={ctx}>
      <div style={{ minHeight: "100dvh", display: "flex", flexDirection: "column", background: "var(--void)" }}>
        <header
          className="bv-web-header"
          style={{
            position: "sticky",
            top: 0,
            zIndex: 20,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "14px 20px",
            borderBottom: "1px solid var(--line)",
            background: "rgba(10,10,15,0.82)",
            backdropFilter: "blur(12px)",
            gap: 12,
          }}
        >
          <Link href="/" style={{ textDecoration: "none" }}>
            <Logo size={20} />
          </Link>
          <nav style={{ display: "flex", gap: 22, alignItems: "center" }} className="bv-web-nav">
            {NAV.map((n) => {
              const active = isActive(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  style={{
                    textDecoration: "none",
                    padding: "6px 2px",
                    fontFamily: "var(--font-sans)",
                    fontSize: 14,
                    fontWeight: active ? 600 : 500,
                    color: active ? "var(--volt)" : "var(--silver)",
                    borderBottom: `2px solid ${active ? "var(--volt)" : "transparent"}`,
                    transition: "all .15s",
                  }}
                >
                  {t(n.key)}
                </Link>
              );
            })}
          </nav>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span
              className="bv-web-actions-extra"
              style={{ display: "flex", alignItems: "center", gap: 14 }}
            >
              <LanguageSwitcher />
              <VersionButton />
            </span>
            {user ? (
              <div style={{ position: "relative" }}>
                <button
                  onClick={() => setMenu((m) => !m)}
                  aria-label="Account menu"
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: "50%",
                    border: "2px solid var(--volt)",
                    background: "var(--obsidian-3)",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: 0,
                  }}
                >
                  <Icon name="user" size={18} color="var(--silver)" />
                </button>
                {menu && (
                  <>
                    <div onClick={() => setMenu(false)} style={{ position: "fixed", inset: 0, zIndex: 29 }} />
                    <div
                      style={{
                        position: "absolute",
                        right: 0,
                        top: 48,
                        zIndex: 30,
                        width: 210,
                        background: "var(--obsidian-2)",
                        border: "1px solid var(--line-strong)",
                        borderRadius: "var(--radius-md)",
                        boxShadow: "var(--shadow-pop)",
                        overflow: "hidden",
                      }}
                    >
                      <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--line)" }}>
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: 600,
                            color: "var(--arctic)",
                            fontFamily: "var(--font-sans)",
                          }}
                        >
                          {user.name}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: "var(--fg3)",
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {user.email}
                        </div>
                      </div>
                      <MenuItem
                        icon="user"
                        label={t("nav.account")}
                        onClick={() => {
                          router.push("/account");
                          setMenu(false);
                        }}
                      />
                      <MenuItem
                        icon="navigation"
                        label={t("nav.trips")}
                        onClick={() => {
                          router.push("/trips");
                          setMenu(false);
                        }}
                      />
                      <MenuItem
                        icon="log-out"
                        label={t("auth.signout")}
                        onClick={() => {
                          ctx.signOut();
                          setMenu(false);
                        }}
                      />
                    </div>
                  </>
                )}
              </div>
            ) : (
              <span className="bv-web-actions-extra">
                <Button variant="ghost" size="sm" onClick={() => openSignIn()}>
                  {t("auth.signin")}
                </Button>
              </span>
            )}
            <Button variant="solid" size="sm" icon="zap" onClick={() => router.push("/book")}>
              {t("home.cta.book")}
            </Button>
          </div>
        </header>

        <main
          className="bv-mobile-pad"
          style={{ flex: 1, width: "100%", maxWidth: 1040, margin: "0 auto", padding: "0 20px" }}
        >
          {children}
        </main>

        <ClientTabBar />
        <InstallHint />
        <ChatAssistant open={chatOpen} setOpen={setChatOpen} />
        {signin && (
          <SignInModal
            onClose={() => setSignin(false)}
            onSignedIn={async (mode) => {
              setSignin(false);
              track("sign_in", { mode });
              let me = null;
              if (mode === "google") {
                me = await fetchMe();
                // A driver/owner signed in on the customer portal. They have no
                // passenger profile, so the client account/booking flow can't work
                // for them (the /me/* endpoints are passenger-only). Send them to
                // their dashboard instead of a broken passenger experience.
                if (me.authenticated && me.role && me.role !== "passenger") {
                  alert(t("auth.driverPortalNotice"));
                  router.push("/dashboard");
                  return;
                }
                const email = me.email || "";
                setUser(
                  me.authenticated
                    ? { name: email ? email.split("@")[0] : "Passenger", email, since: "" }
                    : BV_USER,
                );
                // Surface mandatory agreements right after sign-in (not only on reload).
                setPendingAgreements(me.agreements_pending ?? []);
              } else {
                setUser(BV_USER);
              }
              // Resume the caller's flow (e.g. booking) if one is waiting;
              // otherwise land on the account page.
              const resume = afterSignIn;
              setAfterSignIn(null);
              const cont = () => {
                if (resume) resume();
                else router.push("/account");
              };
              // New passengers must complete their profile (phone + name) before
              // the booking continues. Dismissing the gate cancels the flow.
              if (me && me.authenticated && me.role === "passenger" && me.profile_complete === false) {
                setGateNext(() => cont);
              } else {
                cont();
              }
            }}
          />
        )}

        {gateNext && (
          <ProfileGate
            onClose={() => setGateNext(null)}
            onSaved={() => {
              const cont = gateNext;
              setGateNext(null);
              cont?.();
            }}
          />
        )}

        <footer
          style={{
            padding: "26px 20px 32px",
            textAlign: "center",
            borderTop: "1px solid var(--line)",
            fontSize: 12,
            color: "var(--fg3)",
            fontFamily: "var(--font-sans)",
          }}
        >
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              justifyContent: "center",
              gap: "10px 18px",
              marginBottom: 12,
            }}
          >
            <Link href="/book" style={{ color: "var(--fg2)", textDecoration: "none" }}>
              {t("nav.book")}
            </Link>
            <Link href="/rides" style={{ color: "var(--fg2)", textDecoration: "none" }}>
              {t("nav.rides")}
            </Link>
            <Link href="/blog" style={{ color: "var(--fg2)", textDecoration: "none" }}>
              {t("nav.blog")}
            </Link>
            <InstallButton style={{ color: "var(--fg2)" }} />
            {SEO_ROUTES.slice(0, 4).map((r) => (
              <Link
                key={r.slug}
                href={`/rides/${r.slug}`}
                style={{ color: "var(--fg3)", textDecoration: "none" }}
              >
                {r.shortLabel}
              </Link>
            ))}
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              gap: 14,
              marginBottom: 16,
            }}
          >
            {[
              {
                name: "instagram" as const,
                label: "Instagram",
                href: "https://instagram.com/blackvoltmobility",
              },
              {
                name: "tiktok" as const,
                label: "TikTok",
                href: "https://www.tiktok.com/@blackvoltmobility",
              },
            ].map((s) => (
              <a
                key={s.name}
                href={s.href}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={s.label}
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: "var(--radius-full)",
                  border: "1px solid var(--line-strong)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--silver)",
                }}
              >
                <Icon name={s.name} size={19} color="currentColor" />
              </a>
            ))}
          </div>
          © {t("brand.name")} · {t("footer.area")}
        </footer>
      </div>
    </Ctx.Provider>
  );
}
