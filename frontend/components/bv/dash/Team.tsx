"use client";

/* Team / access list (super-admin only). Add a friend's Google email to grant
   dashboard access, toggle them active/inactive, or remove them. Mirrors the
   dark dashboard card style. */

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import { addMember, listTeam, removeMember, setActive, type TeamMember } from "@/lib/team";

const KNOWN_ERRS = new Set([
  "already_on_list",
  "last_admin",
  "pinned_admin_immutable",
  "invalid_email",
]);

export function Team() {
  const { t } = useI18n();
  const [rows, setRows] = useState<TeamMember[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const errText = (e: unknown): string => {
    const c = e instanceof Error ? e.message : "";
    return t(KNOWN_ERRS.has(c) ? `dash.team.err.${c}` : "dash.team.err.generic");
  };

  const load = () =>
    listTeam()
      .then(setRows)
      .catch((e) => setErr(errText(e)));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const em = email.trim().toLowerCase();
    if (!em || adding) return;
    setAdding(true);
    setErr(null);
    try {
      await addMember(em, name.trim() || undefined);
      setEmail("");
      setName("");
      await load();
    } catch (x) {
      setErr(errText(x));
    } finally {
      setAdding(false);
    }
  };

  const toggle = async (m: TeamMember) => {
    if (m.immutable || busy) return;
    setBusy(m.email);
    setErr(null);
    try {
      await setActive(m.email, !m.active);
      await load();
    } catch (x) {
      setErr(errText(x));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (m: TeamMember) => {
    if (m.immutable || busy) return;
    if (!window.confirm(`${t("dash.team.removeConfirm")} ${m.email}`)) return;
    setBusy(m.email);
    setErr(null);
    try {
      await removeMember(m.email);
      await load();
    } catch (x) {
      setErr(errText(x));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ padding: 28, display: "flex", flexDirection: "column", gap: 18, maxWidth: 720 }}>
      <p style={{ fontSize: 13.5, color: "var(--silver)", margin: 0, lineHeight: 1.55 }}>
        {t("dash.team.subtitle")}
      </p>

      {/* Add form */}
      <form
        onSubmit={add}
        style={{
          background: "var(--obsidian)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-lg)",
          padding: 18,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <div className="bv-team-fields" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Field icon="message-circle" placeholder={t("dash.team.emailPh")} value={email} onChange={setEmail} type="email" grow />
          <Field icon="user" placeholder={t("dash.team.namePh")} value={name} onChange={setName} grow />
        </div>
        <div>
          <Button variant="solid" icon="plus" disabled={adding || !email.trim()} onClick={() => undefined}>
            {adding ? t("dash.team.adding") : t("dash.team.add")}
          </Button>
        </div>
      </form>

      {err && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "rgba(255,92,110,0.08)", border: "1px solid rgba(255,92,110,0.4)", borderRadius: "var(--radius-md)", padding: "10px 13px" }}>
          <Icon name="alert-circle" size={15} color="var(--danger)" />
          <span style={{ fontSize: 12.5, color: "var(--silver)" }}>{err}</span>
        </div>
      )}

      {/* List */}
      <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 6 }}>
        {rows === null ? (
          <div style={{ padding: "30px 0", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}>{t("common.loading")}</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: "30px 0", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}>{t("dash.team.empty")}</div>
        ) : (
          rows.map((m) => (
            <div
              key={m.email}
              style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", borderRadius: "var(--radius-md)" }}
            >
              <div style={{ width: 34, height: 34, borderRadius: "50%", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Icon name={m.role === "admin" ? "shield-check" : "user"} size={16} color="var(--silver)" />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {m.name || m.email.split("@")[0]}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--fg3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {m.email}{m.tenant_slug ? ` · ${m.tenant_slug}` : ""}
                </div>
              </div>
              <Pill tone={m.role === "admin" ? "volt" : "muted"} icon={m.role === "admin" ? "shield-check" : undefined}>
                {t(m.role === "admin" ? "dash.role.admin" : "dash.role.driver")}
              </Pill>
              {m.immutable ? (
                <Pill tone="warning" icon="star">{t("dash.team.owner")}</Pill>
              ) : (
                <>
                  <button
                    onClick={() => toggle(m)}
                    disabled={busy === m.email}
                    title={m.active ? t("dash.team.deactivate") : t("dash.team.activate")}
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px",
                      borderRadius: "var(--radius-full)", cursor: "pointer", fontSize: 12, fontWeight: 600,
                      fontFamily: "var(--font-sans)",
                      background: m.active ? "rgba(43,212,160,0.12)" : "var(--obsidian-3)",
                      color: m.active ? "var(--success)" : "var(--fg3)",
                      border: `1px solid ${m.active ? "rgba(43,212,160,0.4)" : "var(--line-strong)"}`,
                    }}
                  >
                    <Icon name={m.active ? "circle-check" : "circle-dot"} size={13} color="currentColor" />
                    {m.active ? t("dash.team.active") : t("dash.team.inactive")}
                  </button>
                  <button
                    onClick={() => remove(m)}
                    disabled={busy === m.email}
                    title={t("dash.team.remove")}
                    aria-label={t("dash.team.remove")}
                    style={{ background: "none", border: "none", cursor: "pointer", padding: 4, display: "flex", color: "var(--fg3)" }}
                  >
                    <Icon name="x" size={16} color="currentColor" />
                  </button>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function Field({
  icon, placeholder, value, onChange, type, grow,
}: {
  icon: string; placeholder: string; value: string; onChange: (v: string) => void;
  type?: string; grow?: boolean;
}) {
  return (
    <div style={{ flex: grow ? "1 1 220px" : "0 0 auto", display: "flex", alignItems: "center", gap: 8, background: "var(--obsidian-3)", borderRadius: "var(--radius-md)", padding: "9px 11px", border: "1px solid var(--line-strong)", minWidth: 0 }}>
      <Icon name={icon} size={15} color="var(--silver)" />
      <input
        type={type || "text"}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        style={{ flex: 1, minWidth: 0, background: "transparent", border: "none", outline: "none", color: "var(--arctic)", fontSize: 13.5, fontFamily: "var(--font-sans)" }}
      />
    </div>
  );
}
