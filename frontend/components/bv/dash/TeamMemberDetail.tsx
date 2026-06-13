"use client";

/* Team member detail drawer (super-admin): everything about one driver — access,
   subscription, business KPIs, 30-day platform engagement, recent rides + activity
   — plus consolidated management actions. Mirrors ClientDetail's drawer shell. */

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import {
  getTeamMemberDetail,
  removeMember,
  resendInvite,
  setActive,
  setRole,
  type TeamMemberDetail as TMD,
} from "@/lib/team";
import type { RideRow } from "@/lib/booking";
import { StatusPill } from "./DashShell";
import { fmtWhen, uiStatus } from "./status";

const KNOWN_ERRS = new Set([
  "already_on_list",
  "last_admin",
  "pinned_admin_immutable",
  "invalid_email",
]);

const SUB_TONE: Record<string, "success" | "warning" | "muted"> = {
  active: "success",
  pending: "warning",
  past_due: "warning",
  canceled: "muted",
};

const FUNNEL_STAGES = ["book_start", "book_review", "book_pay", "book_confirmed", "sign_in"];

const fmtMoney = (n: number) => (Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`);

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}

function fmtDuration(ms: number): string {
  if (!ms || ms <= 0) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${m}m ${r}s` : `${m}m`;
}

export function TeamMemberDetail({
  email,
  onClose,
  onChanged,
}: {
  email: string;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  const [d, setD] = useState<TMD | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);

  const errText = (e: unknown): string => {
    const c = e instanceof Error ? e.message : "";
    return t(KNOWN_ERRS.has(c) ? `dash.team.err.${c}` : "dash.team.err.generic");
  };

  const load = () =>
    getTeamMemberDetail(email)
      .then(setD)
      .catch(() => setErr("load"));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [email]);

  const act = async (key: string, fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(key);
    setErr(null);
    try {
      await fn();
      onChanged?.();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(null);
    }
  };

  const toggle = () =>
    d &&
    act("active", async () => {
      await setActive(d.email, !d.active);
      await load();
    });

  const changeRole = () => {
    if (!d) return;
    const next = d.role === "admin" ? "driver" : "admin";
    if (next === "admin" && !window.confirm(t("dash.team.promoteConfirm", { email: d.email }))) return;
    return act("role", async () => {
      await setRole(d.email, next);
      await load();
    });
  };

  const remove = () =>
    d &&
    act("remove", async () => {
      await removeMember(d.email);
      onChanged?.();
      onClose();
    });

  const resend = () =>
    d &&
    act("resend", async () => {
      await resendInvite(d.email);
    });

  const copyInvite = () => {
    if (!d) return;
    const link = (typeof window !== "undefined" ? window.location.origin : "") + "/dashboard";
    const msg = t("dash.team.inviteMsg", { email: d.email, link });
    const done = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    };
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(msg).then(done, done);
    else done();
  };

  const isAdmin = d?.role === "admin";

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: 70, background: "rgba(5,5,9,0.72)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}
    >
        <div
          onClick={(e) => e.stopPropagation()}
          style={{ width: "100%", maxWidth: 540, maxHeight: "88dvh", overflowY: "auto", background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-volt)", padding: 24, position: "relative" }}
        >
          <button onClick={onClose} aria-label="Close" style={{ position: "absolute", top: 16, right: 16, background: "none", border: "none", cursor: "pointer", padding: 4 }}>
            <Icon name="x" size={18} color="var(--silver)" />
          </button>

          {!d ? (
            <div style={{ padding: "30px 0", textAlign: "center", color: "var(--fg3)", fontSize: 13 }}>
              {err === "load" ? t("dash.team.detail.loadErr") : t("common.loading")}
            </div>
          ) : (
            <>
              {/* Header */}
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, paddingRight: 24 }}>
                <div style={{ width: 46, height: 46, borderRadius: "50%", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Icon name={isAdmin ? "shield-check" : "user"} size={20} color="var(--silver)" />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 19, color: "var(--arctic)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {d.name || d.email.split("@")[0]}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--fg3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {d.email}{d.tenant_slug ? ` · ${d.tenant_slug}` : ""}
                  </div>
                </div>
                <Pill tone={isAdmin ? "volt" : "muted"} icon={isAdmin ? "shield-check" : "user"}>
                  {t(isAdmin ? "dash.role.admin" : "dash.role.driver")}
                </Pill>
              </div>

              {/* Access line */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginBottom: 16, fontSize: 11.5, color: "var(--fg3)" }}>
                <InlineStat icon={d.active ? "circle-check" : "circle-dot"} text={d.active ? t("dash.team.active") : t("dash.team.inactive")} tone={d.active ? "var(--success)" : "var(--fg3)"} />
                <InlineStat icon="clock" text={`${t("dash.team.lastLogin")}: ${d.last_login ? fmtDate(d.last_login) : t("dash.team.never")}`} />
                <InlineStat icon="calendar" text={`${t("dash.team.detail.memberSince")} ${fmtDate(d.created_at)}`} />
                {d.added_by && <InlineStat icon="user" text={`${t("dash.team.detail.addedBy")} ${d.added_by}`} />}
              </div>

              {/* Management actions */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: d.provisioned ? 20 : 14 }}>
                {!d.immutable && (
                  <>
                    <ActionBtn icon={d.active ? "circle-dot" : "circle-check"} label={d.active ? t("dash.team.deactivate") : t("dash.team.activate")} onClick={toggle} busy={busy === "active"} />
                    <ActionBtn icon={isAdmin ? "user" : "shield-check"} label={isAdmin ? t("dash.team.makeDriver") : t("dash.team.makeAdmin")} onClick={changeRole} busy={busy === "role"} />
                  </>
                )}
                <ActionBtn icon={copied ? "check" : "clipboard"} label={copied ? t("dash.team.copied") : t("dash.team.copyInvite")} onClick={copyInvite} busy={false} />
                <ActionBtn icon="message-circle" label={busy === "resend" ? t("dash.team.resending") : t("dash.team.resend")} onClick={resend} busy={busy === "resend"} />
              </div>

              {err && err !== "load" && (
                <div style={{ display: "flex", alignItems: "center", gap: 8, background: "rgba(255,92,110,0.08)", border: "1px solid rgba(255,92,110,0.4)", borderRadius: "var(--radius-md)", padding: "9px 12px", marginBottom: 16 }}>
                  <Icon name="alert-circle" size={14} color="var(--danger)" />
                  <span style={{ fontSize: 12.5, color: "var(--silver)" }}>{err}</span>
                </div>
              )}

              {!d.provisioned ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: "14px 16px", color: "var(--fg3)", fontSize: 13 }}>
                  <Icon name="clock" size={15} color="var(--fg3)" />
                  {t("dash.team.detail.notProvisioned")}
                </div>
              ) : (
                <>
                  {/* Subscription */}
                  <Section title={t("dash.team.detail.subscription")} />
                  <div style={{ marginBottom: 18 }}>
                    {d.subscription ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: "12px 14px" }}>
                        <Pill tone={SUB_TONE[d.subscription.status] ?? "muted"} icon={d.subscription.paid ? "zap" : undefined}>
                          {d.subscription.plan_key} · {t(`dash.team.detail.sub.${d.subscription.status}`)}
                        </Pill>
                        {d.subscription.current_period_end && (
                          <span style={{ fontSize: 12, color: "var(--fg3)" }}>
                            {t("dash.team.detail.renews")} {fmtDate(d.subscription.current_period_end)}
                          </span>
                        )}
                        {d.subscription.simulated && (
                          <span style={{ fontSize: 11, color: "var(--warning)" }}>{t("dash.team.detail.simulated")}</span>
                        )}
                      </div>
                    ) : (
                      <div style={{ fontSize: 13, color: "var(--fg3)" }}>{t("dash.team.detail.noSub")}</div>
                    )}
                  </div>

                  {/* Business */}
                  <Section title={t("dash.team.detail.business")} />
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 14 }}>
                    <Stat label={t("dash.team.detail.totalRides")} value={String(d.rides.total)} />
                    <Stat label={t("dash.team.detail.completed")} value={String(d.rides.completed)} />
                    <Stat label={t("dash.team.detail.upcoming")} value={String(d.rides.upcoming)} />
                    <Stat label={t("dash.team.detail.revenue")} value={fmtMoney(d.revenue_total)} accent />
                    <Stat label={t("dash.team.detail.clients")} value={String(d.clients)} />
                    <Stat label={t("dash.team.detail.cancelled")} value={String(d.rides.cancelled)} />
                  </div>
                  <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11.5, color: "var(--fg3)", marginBottom: 16 }}>
                    <InlineStat icon="calendar" text={`${t("dash.team.detail.firstRide")}: ${fmtDate(d.first_ride_at)}`} />
                    <InlineStat icon="navigation" text={`${t("dash.team.detail.lastRide")}: ${fmtDate(d.last_ride_at)}`} />
                  </div>

                  {/* Week chart */}
                  <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
                    <span style={{ fontSize: 11.5, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.1em" }}>{t("dash.week")}</span>
                    <span style={{ fontSize: 12, color: "var(--fg3)" }}>{t("dash.week.total")} <strong style={{ fontFamily: "var(--font-display)", color: "var(--volt)" }}>{fmtMoney(d.week_total)}</strong></span>
                  </div>
                  {d.week_total > 0 ? (
                    <div style={{ marginBottom: 20 }}><MiniBars data={d.week} /></div>
                  ) : (
                    <div style={{ fontSize: 13, color: "var(--fg3)", marginBottom: 20 }}>{t("dash.empty.week")}</div>
                  )}

                  {/* Engagement */}
                  <Section title={t("dash.team.detail.engagement")} />
                  {d.engagement && (
                    <>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
                        <Stat label={t("dash.team.detail.sessions")} value={String(d.engagement.sessions)} />
                        <Stat label={t("dash.team.detail.visitors")} value={String(d.engagement.visitors)} />
                        <Stat label={t("dash.team.detail.pageviews")} value={String(d.engagement.pageviews)} />
                        <Stat label={t("dash.team.detail.avgSession")} value={fmtDuration(d.engagement.avg_session_ms)} />
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                        {FUNNEL_STAGES.map((s) => (
                          <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "4px 9px", borderRadius: "var(--radius-full)", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", fontSize: 11, color: "var(--silver)" }}>
                            {t(`dash.team.detail.funnel.${s}`)}
                            <strong style={{ color: "var(--arctic)" }}>{d.engagement!.funnel[s] ?? 0}</strong>
                          </span>
                        ))}
                      </div>
                      {(d.engagement.devices.length > 0 || d.engagement.countries.length > 0) && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, fontSize: 11.5, color: "var(--fg3)", marginBottom: 20 }}>
                          {d.engagement.devices.length > 0 && (
                            <InlineStat icon="settings" text={d.engagement.devices.map((x) => `${x.value} ${x.count}`).join(" · ")} />
                          )}
                          {d.engagement.countries.length > 0 && (
                            <InlineStat icon="globe" text={d.engagement.countries.map((x) => `${x.value} ${x.count}`).join(" · ")} />
                          )}
                        </div>
                      )}
                    </>
                  )}

                  {/* Recent rides */}
                  <Section title={t("dash.team.detail.recentRides")} />
                  {d.recent_rides.length === 0 ? (
                    <div style={{ fontSize: 13, color: "var(--fg3)", marginBottom: 18 }}>{t("dash.team.detail.noRides")}</div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 18 }}>
                      {d.recent_rides.map((r) => (
                        <RideRowItem key={r.id} r={r} />
                      ))}
                    </div>
                  )}

                  {/* Recent activity */}
                  <Section title={t("dash.team.detail.recentActivity")} />
                  {d.recent_activity.length === 0 ? (
                    <div style={{ fontSize: 13, color: "var(--fg3)" }}>{t("dash.team.detail.noActivity")}</div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {d.recent_activity.slice(0, 12).map((e, i) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
                          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--volt)", flexShrink: 0 }} />
                          <span style={{ color: "var(--arctic)", fontWeight: 600 }}>{e.type}</span>
                          {e.path && <span style={{ color: "var(--fg3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.path}</span>}
                          <span style={{ flex: 1 }} />
                          <span style={{ color: "var(--fg3)", flexShrink: 0 }}>{fmtWhen(e.created_at)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* Danger zone: remove access */}
              {!d.immutable && (
                <div style={{ marginTop: 22, paddingTop: 16, borderTop: "1px solid var(--line)" }}>
                  {confirmDel ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      <div style={{ fontSize: 12.5, color: "var(--silver)" }}>{t("dash.team.removeConfirm")} {d.email}?</div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={remove} disabled={busy === "remove"} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: "var(--radius-md)", cursor: "pointer", border: "none", background: "var(--danger)", color: "var(--void)", fontSize: 13, fontWeight: 600, fontFamily: "var(--font-sans)" }}>
                          <Icon name="x" size={14} color="currentColor" />
                          {t("dash.team.remove")}
                        </button>
                        <button onClick={() => setConfirmDel(false)} style={{ padding: "8px 14px", borderRadius: "var(--radius-md)", cursor: "pointer", border: "1px solid var(--line-strong)", background: "transparent", color: "var(--silver)", fontSize: 13, fontWeight: 600, fontFamily: "var(--font-sans)" }}>
                          {t("dash.addClient.cancel")}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => setConfirmDel(true)} style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--danger)", fontFamily: "var(--font-sans)" }}>
                      <Icon name="x" size={14} color="var(--danger)" />
                      {t("dash.team.remove")}
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </div>
    </div>
  );
}

function Section({ title }: { title: string }) {
  return (
    <div style={{ fontSize: 11.5, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>{title}</div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div style={{ background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: "10px 12px" }}>
      <div style={{ fontSize: 11, color: "var(--fg3)" }}>{label}</div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 16, color: accent ? "var(--volt)" : "var(--arctic)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</div>
    </div>
  );
}

function InlineStat({ icon, text, tone }: { icon: string; text: string; tone?: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: tone || "var(--fg3)" }}>
      <Icon name={icon} size={12} color={tone || "var(--fg3)"} />
      {text}
    </span>
  );
}

function ActionBtn({ icon, label, onClick, busy }: { icon: string; label: string; onClick: () => void; busy: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 12px", borderRadius: "var(--radius-full)", cursor: busy ? "default" : "pointer", fontSize: 12, fontWeight: 600, fontFamily: "var(--font-sans)", background: "var(--obsidian-3)", color: "var(--silver)", border: "1px solid var(--line-strong)", opacity: busy ? 0.6 : 1 }}
    >
      <Icon name={icon} size={13} color="currentColor" />
      {label}
    </button>
  );
}

function MiniBars({ data }: { data: { day: string; date: string; revenue: number }[] }) {
  const today = new Date().toDateString();
  const max = Math.max(...data.map((d) => d.revenue), 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 80 }}>
      {data.map((d, i) => {
        const isCurrent = new Date(`${d.date}T00:00`).toDateString() === today;
        return (
          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 7 }}>
            <div title={fmtMoney(d.revenue)} style={{ width: "100%", height: `${Math.max(2, (d.revenue / max) * 60)}px`, borderRadius: 4, background: isCurrent ? "var(--volt)" : "var(--obsidian-3)", boxShadow: isCurrent ? "var(--shadow-volt-sm)" : "none" }} />
            <span style={{ fontSize: 11, color: isCurrent ? "var(--volt)" : "var(--fg3)" }}>{d.day[0]}</span>
          </div>
        );
      })}
    </div>
  );
}

function RideRowItem({ r }: { r: RideRow }) {
  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)" }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: "var(--arctic)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {r.pickup} → {r.dropoff}
        </div>
        <div style={{ fontSize: 11.5, color: "var(--fg3)", marginTop: 2 }}>{fmtWhen(r.scheduled_at)}</div>
      </div>
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 14, color: "var(--volt)" }}>${Math.round(r.fare_total || 0)}</span>
      <StatusPill status={uiStatus(r.status)} />
    </div>
  );
}
