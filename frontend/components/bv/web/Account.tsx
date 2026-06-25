"use client";

import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { ProfileGate } from "./ProfileGate";
import { AddressEditor } from "./AddressEditor";

import { Icon } from "../Icon";
import { Button, GoogleG, Pill, Toggle } from "../ui";
import { useI18n } from "@/lib/i18n";
import { getProfile, updateProfile, type Profile } from "@/lib/profile";
import {
  deleteAddress,
  getAddresses,
  setDefaultAddress,
  type SavedAddress,
} from "@/lib/addresses";
import { useWeb } from "./WebShell";

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14, gap: 10 }}>
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

function IconBtn({ icon, label, onClick, tone }: { icon: string; label: string; onClick: () => void; tone?: "danger" | "default" }) {
  const [h, setH] = useState(false);
  const color = tone === "danger" ? "var(--danger)" : h ? "var(--volt)" : "var(--silver)";
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        width: 38,
        height: 38,
        flexShrink: 0,
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--line-strong)",
        background: h ? "var(--obsidian-2)" : "transparent",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Icon name={icon} size={17} color={color} />
    </button>
  );
}

export function Account() {
  const { t, lang, setLang } = useI18n();
  const { user, signOut, openSignIn } = useWeb();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [addrs, setAddrs] = useState<SavedAddress[]>([]);
  const [editing, setEditing] = useState(false);
  const [editor, setEditor] = useState<{ addr?: SavedAddress } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const langSynced = useRef(false);

  const reloadAddrs = useCallback(() => {
    getAddresses().then(setAddrs).catch(() => {});
  }, []);

  useEffect(() => {
    if (!user) return;
    getProfile()
      .then((p) => {
        setProfile(p);
        // One-time: adopt the server-side language preference on this device.
        if (!langSynced.current && p.lang && p.lang !== lang) {
          setLang(p.lang as "en" | "es");
        }
        langSynced.current = true;
      })
      .catch(() => {});
    reloadAddrs();
  }, [user, lang, setLang, reloadAddrs]);

  // Persist a preference; optimistically update local state, revert on failure.
  async function savePref(patch: Partial<Profile>) {
    if (!profile) return;
    const prev = profile;
    setProfile({ ...profile, ...patch });
    setBusy(true);
    setErr(null);
    try {
      const updated = await updateProfile(patch as Parameters<typeof updateProfile>[0]);
      setProfile(updated);
    } catch (e) {
      setProfile(prev);
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  }

  function pickLang(v: "en" | "es") {
    setLang(v);
    savePref({ lang: v });
  }

  async function onSetDefault(id: number) {
    setBusy(true);
    try {
      await setDefaultAddress(id);
      reloadAddrs();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id: number) {
    if (!window.confirm(t("acct.addr.deleteConfirm"))) return;
    setBusy(true);
    try {
      await deleteAddress(id);
      reloadAddrs();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  }

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

  const displayName = profile?.name || user.name;

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
                {displayName}
              </div>
              <div style={{ fontSize: 13, color: "var(--silver)", display: "flex", alignItems: "center", gap: 7, marginTop: 2 }}>
                <GoogleG size={14} /> {profile?.email || user.email}
              </div>
              {profile?.phone && (
                <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 4 }}>{profile.phone}</div>
              )}
              {profile?.home_address && (
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--fg3)",
                    marginTop: 4,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    minWidth: 0,
                  }}
                >
                  <Icon name="map-pin" size={12} color="var(--fg3)" />
                  <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {t("acct.defaultAddress")}: {profile.home_address}
                  </span>
                </div>
              )}
            </div>
            <Button variant="ghost" size="sm" icon="settings" onClick={() => setEditing(true)}>
              {t("acct.edit")}
            </Button>
          </div>
        </div>

        {err && (
          <div style={{ gridColumn: "1 / -1", fontSize: 13, color: "var(--danger)", fontFamily: "var(--font-sans)" }}>
            {err}
          </div>
        )}

        <div style={{ gridColumn: "1 / -1" }}>
          <Section
            title={t("acct.addresses")}
            action={
              <Button variant="tint" size="sm" icon="plus" onClick={() => setEditor({})}>
                {t("acct.add")}
              </Button>
            }
          >
            {addrs.length === 0 ? (
              <div style={{ fontSize: 13.5, color: "var(--fg3)", fontFamily: "var(--font-sans)", padding: "6px 0" }}>
                {t("acct.addr.empty")}
              </div>
            ) : (
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
                      flexWrap: "wrap",
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
                      <Icon name="map-pin" size={17} color="var(--volt)" />
                    </div>
                    <div style={{ flex: 1, minWidth: 120 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>
                          {a.label || t("acct.addr.untitled")}
                        </span>
                        {a.is_default && (
                          <Pill tone="volt" style={{ fontSize: 10, padding: "2px 8px", letterSpacing: "0.1em" }}>
                            {t("acct.default")}
                          </Pill>
                        )}
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--silver)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {a.address}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                      {!a.is_default && (
                        <IconBtn icon="star" label={t("acct.addr.setDefault")} onClick={() => onSetDefault(a.id)} />
                      )}
                      <IconBtn icon="pencil" label={t("acct.edit")} onClick={() => setEditor({ addr: a })} />
                      <IconBtn icon="trash-2" label={t("acct.addr.delete")} tone="danger" onClick={() => onDelete(a.id)} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>

        <Section title={t("acct.payment")}>
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 13,
              padding: "14px",
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
                flexShrink: 0,
              }}
            >
              <Icon name="lock" size={17} color="var(--volt)" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>
                {t("acct.pay.title")}
              </div>
              <div style={{ fontSize: 12.5, color: "var(--silver)", marginTop: 4, lineHeight: 1.5, fontFamily: "var(--font-sans)" }}>
                {t("acct.pay.body")}
              </div>
            </div>
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
                    onClick={() => pickLang(v)}
                    disabled={busy}
                    style={{
                      padding: "5px 12px",
                      borderRadius: "var(--radius-full)",
                      cursor: busy ? "default" : "pointer",
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
              <Toggle on={!!profile?.sms_consent} setOn={(v) => savePref({ sms_consent: v })} />
            </PrefRow>
            <PrefRow icon="bell" label={t("acct.email")}>
              <Toggle on={!!profile?.email_consent} setOn={(v) => savePref({ email_consent: v })} />
            </PrefRow>
          </div>
        </Section>

        <div style={{ gridColumn: "1 / -1" }}>
          <Button variant="ghost" full icon="log-out" onClick={signOut}>
            {t("auth.signout")}
          </Button>
        </div>
      </div>

      {editing && (
        <ProfileGate
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            getProfile().then(setProfile).catch(() => {});
          }}
        />
      )}

      {editor && (
        <AddressEditor
          initial={editor.addr}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            reloadAddrs();
          }}
        />
      )}
    </div>
  );
}
