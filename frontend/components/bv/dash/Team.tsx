"use client";

/* Team / access list (super-admin only). Add a friend's Google email to grant
   dashboard access, change their role, toggle active/inactive, copy an invite
   message or resend the welcome email, and see per-driver activity. Mirrors the
   dark dashboard card style. */

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import {
  addMember,
  listTeam,
  removeMember,
  resendInvite,
  setActive,
  setRole,
  type TeamMember,
} from "@/lib/team";
import { TeamMemberDetail } from "./TeamMemberDetail";

const KNOWN_ERRS = new Set([
  "already_on_list",
  "last_admin",
  "pinned_admin_immutable",
  "invalid_email",
]);

const fmtMoney = (n: number) => (Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`);

function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}

export function Team() {
  const { t, lang } = useI18n();
  const [rows, setRows] = useState<TeamMember[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [openMember, setOpenMember] = useState<string | null>(null);

  const errText = (e: unknown): string => {
    const c = e instanceof Error ? e.message : "";
    return t(KNOWN_ERRS.has(c) ? `dash.team.err.${c}` : "dash.team.err.generic");
  };

  const emailFlash = (status: string | null | undefined): void => {
    if (status === "sent") setFlash(t("dash.team.emailSent"));
    else if (status === "simulated") setFlash(t("dash.team.emailSimulated"));
    else if (status === "failed") setErr(t("dash.team.emailFailed"));
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
    setFlash(null);
    try {
      const m = await addMember(em, name.trim() || undefined, lang);
      setEmail("");
      setName("");
      emailFlash(m.email_status);
      await load();
    } catch (x) {
      setErr(errText(x));
    } finally {
      setAdding(false);
    }
  };

  const act = async (key: string, fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(key);
    setErr(null);
    setFlash(null);
    try {
      await fn();
    } catch (x) {
      setErr(errText(x));
    } finally {
      setBusy(null);
    }
  };

  const toggle = (m: TeamMember) =>
    act(m.email, async () => {
      await setActive(m.email, !m.active);
      await load();
    });

  const changeRole = (m: TeamMember) => {
    const next = m.role === "admin" ? "driver" : "admin";
    if (next === "admin" && !window.confirm(t("dash.team.promoteConfirm", { email: m.email }))) return;
    return act(m.email, async () => {
      await setRole(m.email, next);
      await load();
    });
  };

  const remove = (m: TeamMember) => {
    if (!window.confirm(`${t("dash.team.removeConfirm")} ${m.email}`)) return;
    return act(m.email, async () => {
      await removeMember(m.email);
      await load();
    });
  };

  const resend = (m: TeamMember) =>
    act(`resend:${m.email}`, async () => {
      const status = await resendInvite(m.email);
      emailFlash(status);
    });

  const copyInvite = (m: TeamMember) => {
    const link = (typeof window !== "undefined" ? window.location.origin : "") + "/dashboard";
    const msg = t("dash.team.inviteMsg", { email: m.email, link });
    const done = () => {
      setCopied(m.email);
      setTimeout(() => setCopied((c) => (c === m.email ? null : c)), 1800);
    };
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(msg).then(done, done);
    else done();
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

      {flash && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "rgba(43,212,160,0.08)", border: "1px solid rgba(43,212,160,0.4)", borderRadius: "var(--radius-md)", padding: "10px 13px" }}>
          <Icon name="circle-check" size={15} color="var(--success)" />
          <span style={{ fontSize: 12.5, color: "var(--silver)" }}>{flash}</span>
        </div>
      )}
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
            <MemberRow
              key={m.email}
              m={m}
              busy={busy}
              copied={copied === m.email}
              onOpen={() => setOpenMember(m.email)}
              onToggle={() => toggle(m)}
              onRole={() => changeRole(m)}
              onRemove={() => remove(m)}
              onResend={() => resend(m)}
              onCopy={() => copyInvite(m)}
            />
          ))
        )}
      </div>

      {openMember && (
        <TeamMemberDetail
          email={openMember}
          onClose={() => setOpenMember(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}

function MemberRow({
  m, busy, copied, onOpen, onToggle, onRole, onRemove, onResend, onCopy,
}: {
  m: TeamMember;
  busy: string | null;
  copied: boolean;
  onOpen: () => void;
  onToggle: () => void;
  onRole: () => void;
  onRemove: () => void;
  onResend: () => void;
  onCopy: () => void;
}) {
  const { t } = useI18n();
  const isAdmin = m.role === "admin";
  const lastLogin = fmtDate(m.last_login);
  const rowBusy = busy === m.email;
  const resending = busy === `resend:${m.email}`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "12px 14px", borderRadius: "var(--radius-md)" }}>
      {/* Identity + role/active row. The identity area opens the detail drawer;
          the role/active/remove controls are separate siblings (no bubbling). */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          onClick={onOpen}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen()}
          title={t("dash.team.detail.open")}
          style={{ display: "flex", alignItems: "center", gap: 12, flex: 1, minWidth: 0, cursor: "pointer" }}
        >
          <div style={{ width: 34, height: 34, borderRadius: "50%", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Icon name={isAdmin ? "shield-check" : "user"} size={16} color="var(--silver)" />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {m.name || m.email.split("@")[0]}
            </div>
            <div style={{ fontSize: 11.5, color: "var(--fg3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {m.email}{m.tenant_slug ? ` · ${m.tenant_slug}` : ""}
            </div>
          </div>
        </div>
        {/* Role pill — clickable to toggle for non-immutable members */}
        {m.immutable ? (
          <Pill tone="volt" icon="shield-check">{t("dash.role.admin")}</Pill>
        ) : (
          <button
            onClick={onRole}
            disabled={rowBusy}
            title={isAdmin ? t("dash.team.makeDriver") : t("dash.team.makeAdmin")}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 11px",
              borderRadius: "var(--radius-full)", cursor: "pointer", fontSize: 12, fontWeight: 600,
              fontFamily: "var(--font-sans)",
              background: isAdmin ? "var(--volt-bg)" : "var(--obsidian-3)",
              color: isAdmin ? "var(--volt)" : "var(--silver)",
              border: `1px solid ${isAdmin ? "var(--volt-border)" : "var(--line-strong)"}`,
            }}
          >
            <Icon name={isAdmin ? "shield-check" : "user"} size={13} color="currentColor" />
            {t(isAdmin ? "dash.role.admin" : "dash.role.driver")}
          </button>
        )}
        {m.immutable ? (
          <Pill tone="warning" icon="star">{t("dash.team.owner")}</Pill>
        ) : (
          <>
            <button
              onClick={onToggle}
              disabled={rowBusy}
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
              onClick={onRemove}
              disabled={rowBusy}
              title={t("dash.team.remove")}
              aria-label={t("dash.team.remove")}
              style={{ background: "none", border: "none", cursor: "pointer", padding: 4, display: "flex", color: "var(--fg3)" }}
            >
              <Icon name="x" size={16} color="currentColor" />
            </button>
          </>
        )}
      </div>

      {/* Stats + secondary actions */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", paddingLeft: 46 }}>
        <Stat icon="navigation" text={`${m.rides} ${t("dash.team.rides")}`} />
        {m.revenue > 0 && <Stat icon="dollar-sign" text={fmtMoney(m.revenue)} />}
        <Stat icon="clock" text={`${t("dash.team.lastLogin")}: ${lastLogin || t("dash.team.never")}`} />
        <div style={{ flex: 1 }} />
        <RowAction icon={copied ? "check" : "clipboard"} label={copied ? t("dash.team.copied") : t("dash.team.copyInvite")} onClick={onCopy} disabled={false} />
        <RowAction icon="message-circle" label={resending ? t("dash.team.resending") : t("dash.team.resend")} onClick={onResend} disabled={resending} />
      </div>
    </div>
  );
}

function Stat({ icon, text }: { icon: string; text: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, color: "var(--fg3)", whiteSpace: "nowrap" }}>
      <Icon name={icon} size={12} color="var(--fg3)" />
      {text}
    </span>
  );
}

function RowAction({ icon, label, onClick, disabled }: { icon: string; label: string; onClick: () => void; disabled: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "inline-flex", alignItems: "center", gap: 5, padding: "4px 9px",
        borderRadius: "var(--radius-full)", cursor: disabled ? "default" : "pointer",
        fontSize: 11, fontWeight: 600, fontFamily: "var(--font-sans)",
        background: "transparent", color: "var(--silver)", border: "1px solid var(--line-strong)",
        opacity: disabled ? 0.6 : 1,
      }}
    >
      <Icon name={icon} size={12} color="currentColor" />
      {label}
    </button>
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
