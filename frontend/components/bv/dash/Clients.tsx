"use client";

import { useEffect, useState } from "react";

import { Icon } from "../Icon";
import { Button, Field, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import { useViewport } from "@/lib/useViewport";
import { createClient, listClients, type ClientRow } from "@/lib/dashboard";
import { EmptyState } from "./Overview";
import { ClientDetail } from "./ClientDetail";

const TIER_TONE: Record<string, "volt" | "muted" | "success"> = {
  VIP: "volt",
  Regular: "muted",
  New: "success",
};

function ClientRowView({ c, onOpen }: { c: ClientRow; onOpen: (id: number) => void }) {
  const { t } = useI18n();
  const [h, setH] = useState(false);
  const { compact } = useViewport();

  if (compact) {
    return (
      <div
        onClick={() => onOpen(c.id)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen(c.id)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "13px 14px",
          margin: "0 6px 8px",
          background: "var(--obsidian-2)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-lg)",
          cursor: "pointer",
        }}
      >
        <div
          style={{
            width: 38,
            height: 38,
            borderRadius: "50%",
            background: "var(--obsidian-3)",
            border: "1px solid var(--line-strong)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Icon name="user" size={17} color="var(--silver)" />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>{c.name}</span>
            <Pill tone={TIER_TONE[c.tier]} icon={c.tier === "VIP" ? "star" : undefined}>
              {t(`dash.tier.${c.tier}`)}
            </Pill>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--silver)", margin: "3px 0 2px" }}>{c.phone || c.email || "—"}</div>
          <div style={{ fontSize: 11.5, color: "var(--fg3)" }}>
            {c.rides_count} {t("dash.col.rides").toLowerCase()} · ${c.lifetime_spend.toLocaleString()} · {t("dash.prefers", { lang: c.lang })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      onClick={() => onOpen(c.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen(c.id)}
      style={{
        display: "grid",
        gridTemplateColumns: "1.4fr 1fr 80px 110px 90px",
        gap: 14,
        alignItems: "center",
        padding: "13px 16px",
        borderRadius: "var(--radius-md)",
        background: h ? "var(--obsidian-2)" : "transparent",
        transition: "background .12s",
        minWidth: 620,
        cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: "50%",
            background: "var(--obsidian-3)",
            border: "1px solid var(--line-strong)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Icon name="user" size={16} color="var(--silver)" />
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", fontFamily: "var(--font-sans)" }}>{c.name}</div>
          <div style={{ fontSize: 11, color: "var(--fg3)" }}>{t("dash.prefers", { lang: c.lang })}</div>
        </div>
      </div>
      <div style={{ fontSize: 13, color: "var(--silver)" }}>{c.phone || c.email || "—"}</div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 15, color: "var(--arctic)" }}>{c.rides_count}</div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 15, color: "var(--arctic)" }}>${c.lifetime_spend.toLocaleString()}</div>
      <Pill tone={TIER_TONE[c.tier]} icon={c.tier === "VIP" ? "star" : undefined}>
        {t(`dash.tier.${c.tier}`)}
      </Pill>
    </div>
  );
}

export function Clients() {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<number | null>(null);
  const [reload, setReload] = useState(0);
  const [addOpen, setAddOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    listClients()
      .then((cs) => alive && setClients(cs))
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [reload]);

  const needle = q.toLowerCase().trim();
  const shown = clients.filter(
    (c) =>
      c.name.toLowerCase().includes(needle) ||
      (c.phone || "").toLowerCase().includes(needle) ||
      (c.email || "").toLowerCase().includes(needle),
  );

  return (
    <div style={{ padding: 28 }}>
      <div style={{ marginBottom: 18, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 220px", maxWidth: 320 }}>
          <Field icon="search" placeholder={t("dash.searchClients")} value={q} onChange={setQ} />
        </div>
        <Button variant="solid" icon="plus" onClick={() => setAddOpen(true)}>
          {t("dash.addClient")}
        </Button>
      </div>
      <div
        className="bv-table-wrap"
        style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 6, overflowX: "auto" }}
      >
        <div
          className="bv-table-head"
          style={{
            display: "grid",
            gridTemplateColumns: "1.4fr 1fr 80px 110px 90px",
            gap: 14,
            padding: "12px 16px",
            fontSize: 11,
            color: "var(--fg3)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            borderBottom: "1px solid var(--line)",
            minWidth: 620,
          }}
        >
          <span>{t("dash.col.client")}</span>
          <span>{t("dash.col.phone")}</span>
          <span>{t("dash.col.rides")}</span>
          <span>{t("dash.col.lifetime")}</span>
          <span>{t("dash.col.tier")}</span>
        </div>
        {loading ? (
          <EmptyState icon="users" text={t("common.loading")} />
        ) : shown.length === 0 ? (
          <EmptyState icon="users" text={t("dash.empty.clients")} />
        ) : (
          shown.map((c) => <ClientRowView key={c.id} c={c} onOpen={setDetail} />)
        )}
      </div>

      {detail != null && (
        <ClientDetail
          clientId={detail}
          onClose={() => setDetail(null)}
          onChanged={() => setReload((n) => n + 1)}
        />
      )}

      {addOpen && (
        <AddClientModal
          onClose={() => setAddOpen(false)}
          onCreated={() => {
            setAddOpen(false);
            setReload((n) => n + 1);
          }}
        />
      )}
    </div>
  );
}

function AddClientModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { t } = useI18n();
  const [form, setForm] = useState({ name: "", phone: "", email: "", lang: "EN" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const create = async () => {
    if (busy || !form.name.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await createClient({
        name: form.name.trim(),
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        lang: form.lang,
      });
      onCreated();
    } catch (e) {
      setErr(e instanceof Error && e.message ? e.message : "create");
      setBusy(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: 70, background: "rgba(5,5,9,0.72)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 440, background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-volt)", padding: 24, position: "relative" }}
      >
        <button onClick={onClose} aria-label="Close" style={{ position: "absolute", top: 16, right: 16, background: "none", border: "none", cursor: "pointer", padding: 4 }}>
          <Icon name="x" size={18} color="var(--silver)" />
        </button>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 19, color: "var(--arctic)", marginBottom: 18 }}>
          {t("dash.addClient.title")}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
          <Field icon="user" label={t("dash.client.name")} placeholder={t("dash.addClient.namePh")} value={form.name} onChange={(v) => set("name", v)} />
          <Field icon="phone" label={t("dash.client.phone")} placeholder={t("dash.addClient.phonePh")} value={form.phone} onChange={(v) => set("phone", v)} />
          <Field icon="message-circle" label={t("dash.client.email")} placeholder={t("dash.addClient.emailPh")} value={form.email} onChange={(v) => set("email", v)} />
          <div>
            <div style={{ fontSize: 11.5, color: "var(--fg3)", marginBottom: 5 }}>{t("dash.client.language")}</div>
            <div style={{ display: "flex", gap: 4, background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: 4, width: "fit-content" }}>
              {["EN", "ES"].map((v) => (
                <button
                  key={v}
                  onClick={() => set("lang", v)}
                  style={{ padding: "6px 16px", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600, border: "none", fontFamily: "var(--font-sans)", background: form.lang === v ? "var(--volt-bg-20)" : "transparent", color: form.lang === v ? "var(--volt)" : "var(--silver)" }}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
        </div>
        {err && (
          <div style={{ fontSize: 12.5, color: "var(--danger)", marginBottom: 12, display: "flex", alignItems: "flex-start", gap: 6 }}>
            <Icon name="alert-circle" size={14} color="var(--danger)" />
            <span>{err === "create" ? t("dash.addClient.err") : err}</span>
          </div>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="solid" icon="circle-check" disabled={!form.name.trim() || busy} onClick={create}>
            {busy ? t("dash.addClient.creating") : t("dash.addClient.create")}
          </Button>
          <Button variant="ghost" disabled={busy} onClick={onClose}>
            {t("dash.addClient.cancel")}
          </Button>
        </div>
      </div>
    </div>
  );
}
