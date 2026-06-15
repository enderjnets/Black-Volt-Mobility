"use client";

import { type ReactNode, useState } from "react";

import { Icon } from "../Icon";
import { Button, GoogleG, Pill, Toggle } from "../ui";
import { useI18n } from "@/lib/i18n";
import { useWeb } from "./WebShell";

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16, color: "var(--arctic)" }}>{title}</span>
        {action}
      </div>
      {children}
    </div>
  );
}

function PrefRow({ icon, label, children }: { icon: string; label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
      <Icon name={icon} size={18} color="var(--silver)" />
      <span style={{ flex: 1, fontSize: 14, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>{label}</span>
      {children}
    </div>
  );
}

export function Account() {
  const { t, lang, setLang } = useI18n();
  const { user, signOut, openSignIn } = useWeb();
  const [addrs] = useState([
    { id: 1, label: t("acct.home"), icon: "map-pin", text: "1450 Larimer St, Denver, CO", def: true },
    { id: 2, label: t("acct.work"), icon: "navigation", text: "1801 California St, Denver, CO", def: false },
    { id: 3, label: "Airport", icon: "plane", text: "Denver Intl (DEN) · Arrivals", def: false },
  ]);
  const [sms, setSms] = useState(true);
  const [email, setEmail] = useState(true);

  if (!user) {
    return (
      <div style={{ maxWidth: 420, margin: "80px auto", textAlign: "center" }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--arctic)", marginBottom: 14 }}>
          {t("acct.title")}
        </h2>
        <p style={{ color: "var(--silver)", marginBottom: 20 }}>{t("auth.subtitle")}</p>
        <Button variant="solid" icon="zap" onClick={() => openSignIn()}>
          {t("auth.signin")}
        </Button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "32px 0" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 28, color: "var(--arctic)", margin: "0 0 20px" }}>
        {t("acct.title")}
      </h2>

      <div className="bv-acct-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, alignItems: "start" }}>
        <div style={{ gridColumn: "1 / -1" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              background: "var(--obsidian)",
              border: "1px solid var(--volt-border)",
              borderRadius: "var(--radius-lg)",
              padding: 20,
              boxShadow: "var(--shadow-volt-sm)",
            }}
          >
            <div
              style={{
                width: 58,
                height: 58,
                borderRadius: "50%",
                border: "2px solid var(--volt)",
                background: "var(--obsidian-3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <Icon name="user" size={26} color="var(--silver)" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, color: "var(--arctic)" }}>
                {user.name}
              </div>
              <div style={{ fontSize: 13, color: "var(--silver)", display: "flex", alignItems: "center", gap: 7, marginTop: 2 }}>
                <GoogleG size={14} /> {user.email}
              </div>
              <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 4 }}>
                {t("acct.member")} {user.since}
              </div>
            </div>
            <Button variant="ghost" size="sm" icon="settings">
              {t("acct.edit")}
            </Button>
          </div>
        </div>

        <div style={{ gridColumn: "1 / -1" }}>
          <Section
            title={t("acct.addresses")}
            action={
              <Button variant="tint" size="sm" icon="plus">
                {t("acct.add")}
              </Button>
            }
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {addrs.map((a) => (
                <div
                  key={a.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 13,
                    padding: "12px 14px",
                    background: "var(--obsidian-3)",
                    border: "1px solid var(--line-strong)",
                    borderRadius: "var(--radius-md)",
                  }}
                >
                  <div
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: 9,
                      background: "var(--volt-bg)",
                      border: "1px solid var(--volt-border)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <Icon name={a.icon} size={17} color="var(--volt)" />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>
                        {a.label}
                      </span>
                      {a.def && (
                        <Pill tone="volt" style={{ fontSize: 10, padding: "2px 8px", letterSpacing: "0.1em" }}>
                          {t("acct.default")}
                        </Pill>
                      )}
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--silver)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {a.text}
                    </div>
                  </div>
                  <Icon name="more-horizontal" size={18} color="var(--fg3)" />
                </div>
              ))}
            </div>
          </Section>
        </div>

        <Section title={t("acct.payment")}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 13,
              padding: "12px 14px",
              background: "var(--obsidian-3)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 9,
                background: "var(--obsidian-2)",
                border: "1px solid var(--line-strong)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Icon name="credit-card" size={17} color="var(--silver)" />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)" }}>Visa ···· 4242</div>
              <div style={{ fontSize: 12, color: "var(--fg3)" }}>via Square · expires 09/28</div>
            </div>
            <Icon name="check" size={18} color="var(--success)" />
          </div>
        </Section>

        <Section title={t("acct.prefs")}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <PrefRow icon="globe" label={t("acct.lang")}>
              <div style={{ display: "flex", gap: 6 }}>
                {(
                  [
                    ["en", "EN"],
                    ["es", "ES"],
                  ] as const
                ).map(([v, l]) => (
                  <button
                    key={v}
                    onClick={() => setLang(v)}
                    style={{
                      padding: "5px 12px",
                      borderRadius: "var(--radius-full)",
                      cursor: "pointer",
                      fontSize: 12,
                      fontWeight: 600,
                      background: lang === v ? "var(--volt-bg-20)" : "var(--obsidian-3)",
                      color: lang === v ? "var(--volt)" : "var(--silver)",
                      border: `1px solid ${lang === v ? "var(--volt-border)" : "var(--line-strong)"}`,
                    }}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </PrefRow>
            <PrefRow icon="message-circle" label={t("acct.sms")}>
              <Toggle on={sms} setOn={setSms} />
            </PrefRow>
            <PrefRow icon="bell" label={t("acct.email")}>
              <Toggle on={email} setOn={setEmail} />
            </PrefRow>
          </div>
        </Section>

        <div style={{ gridColumn: "1 / -1" }}>
          <Button variant="ghost" full icon="log-out" onClick={signOut}>
            {t("auth.signout")}
          </Button>
        </div>
      </div>
    </div>
  );
}
