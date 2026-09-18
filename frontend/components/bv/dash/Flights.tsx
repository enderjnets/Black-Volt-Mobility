"use client";

/* Flights — the driver's own flights, soonest first.
 *
 * Phase A: everything that can be known from the rides themselves. There is no live
 * status yet, and the card says so rather than dressing a guess up as a schedule.
 *
 * Every time here is rendered in Denver time on purpose. Both ends of these rides are
 * DEN, and the rest of the dashboard formats in the browser's zone — which quietly
 * shifts every hour on screen if he opens the dashboard on a laptop still set to
 * Pacific. A pickup hour that is wrong by one hour is worse than no pickup hour.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { Icon } from "../Icon";
import { EmptyState, fmtCountdown } from "./Overview";
import { updateRide } from "@/lib/booking";
import {
  DEN_CARRIERS,
  listUpcomingFlights,
  type UpcomingFlight,
  type UpcomingFlights,
} from "@/lib/flights";
import { useI18n } from "@/lib/i18n";
import { openMapsTo } from "@/lib/maps";
import { useViewport } from "@/lib/useViewport";

const TZ = "America/Denver";

function hhmm(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: TZ,
  }).format(d);
}

/** Denver-local calendar day, as a stable key for the date separators. */
function dayKey(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: TZ,
  }).format(d);
}

function dayLabel(iso: string, locale: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(locale === "es" ? "es-ES" : "en-US", {
    weekday: "long",
    day: "numeric",
    month: "short",
    timeZone: TZ,
  }).format(d);
}

function StatusChip({ f, t }: { f: UpcomingFlight; t: (k: string) => string }) {
  if (f.needs_airline) {
    return (
      <span
        style={{
          flexShrink: 0,
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "3px 10px",
          borderRadius: "var(--radius-full)",
          background: "rgba(255,194,75,0.12)",
          border: "1px solid rgba(255,194,75,0.35)",
          color: "var(--warning)",
          fontSize: 10.5,
          fontWeight: 600,
          letterSpacing: "0.06em",
          whiteSpace: "nowrap",
        }}
      >
        <Icon name="alert-circle" size={11} color="var(--warning)" />
        {t("dash.flights.chip.noAirline")}
      </span>
    );
  }
  return (
    <span
      style={{
        flexShrink: 0,
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 10px",
        borderRadius: "var(--radius-full)",
        background: "var(--obsidian-3)",
        border: "1px solid var(--line-strong)",
        color: "var(--fg3)",
        fontSize: 10.5,
        fontWeight: 600,
        letterSpacing: "0.06em",
        whiteSpace: "nowrap",
      }}
    >
      {t("dash.flights.chip.noLive")}
    </span>
  );
}

function Row({
  f,
  selected,
  onOpen,
  t,
}: {
  f: UpcomingFlight;
  selected: boolean;
  onOpen: () => void;
  t: (k: string) => string;
}) {
  const [h, setH] = useState(false);
  const hot = selected || h;
  return (
    <button
      type="button"
      onClick={onOpen}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      aria-current={selected ? "true" : undefined}
      style={{
        all: "unset",
        boxSizing: "border-box",
        display: "block",
        width: "100%",
        cursor: "pointer",
        padding: "13px 15px",
        borderRadius: "var(--radius-lg)",
        background: selected ? "var(--volt-bg)" : hot ? "var(--obsidian-2)" : "var(--obsidian)",
        border: `1px solid ${selected ? "var(--volt-border)" : "var(--line-strong)"}`,
        boxShadow: selected ? "var(--shadow-volt-sm)" : "none",
        transition: "background .12s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          style={{
            flexShrink: 0,
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 19,
            color: "var(--arctic)",
          }}
        >
          {f.code}
        </span>
        <span style={{ flexGrow: 1 }} />
        <StatusChip f={f} t={t} />
      </div>
      <div style={{ fontSize: 11.5, color: "var(--fg3)", marginTop: 3 }}>
        {f.airline || t("dash.flights.row.unknownAirline")}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginTop: 9,
          fontSize: 13,
          color: "var(--silver)",
        }}
      >
        <Icon
          name={f.direction === "arrival" ? "arrow-left" : "arrow-right"}
          size={13}
          color="var(--volt)"
        />
        <span style={{ flexShrink: 0 }}>
          {t(f.direction === "arrival" ? "dash.flights.dir.arrival" : "dash.flights.dir.departure")}
        </span>
        <span style={{ flexShrink: 0, color: "var(--fg3)" }}>·</span>
        <span style={{ flexShrink: 0 }}>{hhmm(f.scheduled_at)}</span>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginTop: 9,
          paddingTop: 9,
          borderTop: `1px solid ${selected ? "rgba(0,229,255,0.2)" : "var(--line)"}`,
        }}
      >
        <span
          style={{
            flexGrow: 1,
            minWidth: 0,
            fontSize: 11.5,
            color: "var(--fg3)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {f.client || t("dash.ride.guest")} · BV-{f.ride_id}
        </span>
        <span
          style={{
            flexShrink: 0,
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 14,
            color: selected ? "var(--volt)" : "var(--fg3)",
          }}
        >
          {fmtCountdown(f.scheduled_at, t("dash.next.now"))}
        </span>
      </div>
    </button>
  );
}

function CarrierPicker({
  f,
  onDone,
  t,
}: {
  f: UpcomingFlight;
  onDone: () => void;
  t: (k: string) => string;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState(false);

  const pick = async (code: string) => {
    setBusy(code);
    setErr(false);
    try {
      await updateRide(f.ride_id, { flight_number: `${code} ${f.number}` });
      onDone();
    } catch {
      setErr(true);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      style={{
        boxSizing: "border-box",
        padding: 18,
        borderRadius: "var(--radius-lg)",
        background: "var(--obsidian-2)",
        border: "1px solid rgba(255,194,75,0.35)",
      }}
    >
      <div style={{ fontSize: 13, color: "var(--silver)", lineHeight: 1.5 }}>
        {t("dash.flights.noAirline.why")}
      </div>
      <div
        style={{
          fontSize: 11,
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          color: "var(--fg3)",
          margin: "14px 0 9px",
        }}
      >
        {t("dash.flights.noAirline.ask")}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {DEN_CARRIERS.map((c) => (
          <button
            key={c.code}
            type="button"
            onClick={() => pick(c.code)}
            disabled={busy !== null}
            title={c.name}
            style={{
              all: "unset",
              boxSizing: "border-box",
              flexShrink: 0,
              cursor: busy ? "default" : "pointer",
              display: "inline-flex",
              alignItems: "center",
              minHeight: 44,
              padding: "0 15px",
              borderRadius: "var(--radius-full)",
              background: busy === c.code ? "var(--volt-bg)" : "var(--obsidian)",
              border: "1px solid var(--line-strong)",
              color: "var(--silver)",
              fontSize: 12.5,
              opacity: busy && busy !== c.code ? 0.5 : 1,
            }}
          >
            {c.code} {f.number}
          </button>
        ))}
      </div>
      {err && (
        <div style={{ color: "#ff7a7a", fontSize: 12.5, marginTop: 12 }}>
          {t("dash.flights.noAirline.err")}
        </div>
      )}
      <div style={{ fontSize: 11, color: "var(--fg3)", marginTop: 12 }}>
        {t("dash.flights.noAirline.saved")}
      </div>
    </div>
  );
}

function Detail({
  f,
  onChanged,
  t,
}: {
  f: UpcomingFlight;
  onChanged: () => void;
  t: (k: string) => string;
}) {
  const label = (s: string) => (
    <div
      style={{
        fontSize: 11,
        letterSpacing: "0.1em",
        textTransform: "uppercase",
        color: "var(--fg3)",
      }}
    >
      {s}
    </div>
  );

  return (
    <section
      aria-label={f.code}
      style={{
        boxSizing: "border-box",
        padding: 24,
        borderRadius: "var(--radius-lg)",
        background: "var(--obsidian)",
        border: "1px solid var(--volt-border)",
        boxShadow: "var(--shadow-volt-sm)",
        display: "flex",
        flexDirection: "column",
        gap: 18,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
        <div style={{ flexGrow: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 700,
              fontSize: 34,
              lineHeight: 1.05,
              letterSpacing: "0.02em",
              color: "var(--arctic)",
            }}
          >
            {f.code}
          </div>
          <div style={{ fontSize: 13, color: "var(--silver)", marginTop: 2 }}>
            {f.airline || t("dash.flights.row.unknownAirline")}
          </div>
        </div>
        <StatusChip f={f} t={t} />
      </div>

      {f.needs_airline ? (
        <CarrierPicker f={f} onDone={onChanged} t={t} />
      ) : (
        <div
          style={{
            boxSizing: "border-box",
            padding: "22px 16px",
            borderRadius: "var(--radius-lg)",
            background: "var(--obsidian-2)",
            border: "1px dashed var(--line-strong)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 9,
          }}
        >
          <Icon name="plane" size={26} color="var(--fg3)" strokeWidth={1.6} />
          <div
            style={{
              fontSize: 12.5,
              color: "var(--silver)",
              textAlign: "center",
              lineHeight: 1.5,
              maxWidth: 360,
            }}
          >
            {t("dash.flights.noLive.body")}
          </div>
        </div>
      )}

      <div
        style={{
          boxSizing: "border-box",
          padding: "18px 20px",
          borderRadius: "var(--radius-lg)",
          background: "rgba(0,229,255,0.06)",
          border: "1px solid var(--volt-border)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              flexShrink: 0,
              fontSize: 11,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--volt)",
            }}
          >
            {t("dash.flights.yourRide")}
          </span>
          <span
            style={{
              flexGrow: 1,
              minWidth: 0,
              fontSize: 12.5,
              color: "var(--silver)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {f.client || t("dash.ride.guest")} · BV-{f.ride_id}
          </span>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 9,
            marginTop: 10,
            fontSize: 13,
            color: "var(--silver)",
            flexWrap: "wrap",
          }}
        >
          <Icon name="circle-dot" size={14} color="var(--volt)" />
          <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
            {f.pickup}
          </span>
          <Icon name="arrow-right" size={13} color="var(--fg3)" />
          <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
            {f.dropoff}
          </span>
          {f.distance_miles != null && (
            <span style={{ flexShrink: 0, color: "var(--fg3)" }}>
              · {f.distance_miles} mi
              {f.duration_minutes != null ? ` · ${Math.round(f.duration_minutes)} min` : ""}
            </span>
          )}
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 16,
            marginTop: 14,
            paddingTop: 14,
            borderTop: "1px solid rgba(0,229,255,0.2)",
            flexWrap: "wrap",
          }}
        >
          <div style={{ flexGrow: 1, minWidth: 0 }}>
            {label(t("dash.flights.pickupAt"))}
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 700,
                fontSize: 38,
                lineHeight: 1.05,
                color: "var(--volt)",
                marginTop: 2,
              }}
            >
              {hhmm(f.scheduled_at)}
            </div>
            <div style={{ fontSize: 11.5, color: "var(--fg3)", marginTop: 2 }}>
              {f.airport_eta
                ? `${t("dash.flights.terminalBy")} ${hhmm(f.airport_eta)} · ${t("dash.flights.tz")}`
                : t("dash.flights.tz")}
            </div>
          </div>
          <button
            type="button"
            onClick={() => openMapsTo(f.pickup)}
            aria-label={t("dash.flights.navigate")}
            title={t("dash.flights.navigate")}
            style={{
              all: "unset",
              boxSizing: "border-box",
              flexShrink: 0,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 9,
              minHeight: 44,
              padding: "0 20px",
              borderRadius: "var(--radius-full)",
              background: "var(--volt)",
              color: "var(--void)",
              fontSize: 13.5,
              fontWeight: 700,
            }}
          >
            <Icon name="navigation" size={16} color="var(--void)" />
            {t("dash.flights.navigate")}
          </button>
        </div>
      </div>
    </section>
  );
}

export function Flights() {
  const { t, lang } = useI18n();
  const { compact } = useViewport();
  const [data, setData] = useState<UpcomingFlights | null>(null);
  const [err, setErr] = useState(false);
  const [loading, setLoading] = useState(true);
  const [picked, setPicked] = useState<number | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    setErr(false);
    setLoading(true);
    listUpcomingFlights()
      .then((d) => {
        if (!alive) return;
        setData(d);
        setPicked((cur) =>
          cur != null && d.flights.some((f) => f.ride_id === cur)
            ? cur
            : (d.flights[0]?.ride_id ?? null),
        );
      })
      .catch(() => alive && setErr(true))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [reload]);

  const refresh = useCallback(() => setReload((n) => n + 1), []);

  const groups = useMemo(() => {
    const out: { key: string; label: string; items: UpcomingFlight[] }[] = [];
    for (const f of data?.flights ?? []) {
      const k = dayKey(f.scheduled_at);
      const last = out[out.length - 1];
      if (last && last.key === k) last.items.push(f);
      else out.push({ key: k, label: dayLabel(f.scheduled_at, lang), items: [f] });
    }
    return out;
  }, [data, lang]);

  const selected = data?.flights.find((f) => f.ride_id === picked) ?? null;

  const header = (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
      <div style={{ flexGrow: 1, minWidth: 0 }}>
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg3)" }}>
          {t("dash.flights.subtitle")}
        </p>
      </div>
      {data && data.flights.length > 0 && (
        <div
          style={{
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: 11,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--fg3)",
          }}
        >
          <Icon name="clock" size={13} color="var(--fg3)" />
          {data.flights.length} · {data.window_hours} h
        </div>
      )}
    </div>
  );

  const list = (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {groups.map((g) => (
        <div key={g.key} style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--fg3)",
              paddingLeft: 2,
              marginTop: 6,
            }}
          >
            {g.label}
          </div>
          {g.items.map((f) => (
            <Row
              key={f.ride_id}
              f={f}
              selected={f.ride_id === picked}
              onOpen={() => setPicked(f.ride_id)}
              t={t}
            />
          ))}
        </div>
      ))}
    </div>
  );

  return (
    <div style={{ padding: 28, display: "flex", flexDirection: "column", gap: 22 }}>
      {header}

      {loading ? (
        <EmptyState icon="plane" text={t("common.loading")} />
      ) : err ? (
        <div style={{ color: "#ff7a7a", fontSize: 13 }}>{t("dash.flights.err")}</div>
      ) : !data || data.flights.length === 0 ? (
        <EmptyState icon="plane" text={t("dash.flights.empty")} />
      ) : compact ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {list}
          {selected && <Detail f={selected} onChanged={refresh} t={t} />}
        </div>
      ) : (
        <div
          className="bv-dash-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1.35fr",
            gap: 20,
            alignItems: "start",
          }}
        >
          {list}
          {selected && <Detail f={selected} onChanged={refresh} t={t} />}
        </div>
      )}

      {data && data.skipped.no_scheduled_time > 0 && (
        <div style={{ fontSize: 11.5, color: "var(--fg3)" }}>
          {t("dash.flights.skippedNoTime")} · {data.skipped.no_scheduled_time}
        </div>
      )}
    </div>
  );
}
