"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { Icon } from "../Icon";
import { Button, Logo } from "../ui";
import { VersionButton } from "../../ui/VersionButton";
import { LanguageSwitcher } from "../../ui/LanguageSwitcher";
import { useI18n } from "@/lib/i18n";
import { fetchMe, logout } from "@/lib/auth";
import { track } from "@/lib/analytics";
import { ChatAssistant } from "./Chat";
import { ClientTabBar } from "./ClientTabBar";
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

  return (
    <Ctx.Provider value={ctx}>
      <div style={{ minHeight: "100dvh", display: "flex", flexDirection: "column", background: "var(--void)" }}>
        <header
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
            <LanguageSwitcher />
            <VersionButton />
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
              <Button variant="ghost" size="sm" onClick={() => openSignIn()}>
                {t("auth.signin")}
              </Button>
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

        {pendingAgreements.length > 0 && (
          <AgreementGate pending={pendingAgreements} onComplete={refreshMe} />
        )}

        <footer
          style={{
            padding: "22px 20px",
            textAlign: "center",
            borderTop: "1px solid var(--line)",
            fontSize: 12,
            color: "var(--fg3)",
            fontFamily: "var(--font-sans)",
          }}
        >
          © {t("brand.name")} · Denver / Aurora, CO
        </footer>
      </div>
    </Ctx.Provider>
  );
}
