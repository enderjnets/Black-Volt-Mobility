"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Icon } from "../Icon";
import { Button, Card, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import { getPublicProfile, type PublicProfile } from "@/lib/tenant";

function FauxQR({ size = 132 }: { size?: number }) {
  const n = 11;
  const cells: boolean[] = [];
  for (let r = 0; r < n; r++)
    for (let c = 0; c < n; c++) {
      const corner = (r < 3 && c < 3) || (r < 3 && c > n - 4) || (r > n - 4 && c < 3);
      const on = corner || (r * 7 + c * 13 + r * c * 3) % 5 < 2;
      cells.push(on);
    }
  return (
    <div style={{ background: "var(--arctic)", padding: 10, borderRadius: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${n}, 1fr)`, gap: 2, width: size, height: size }}>
        {cells.map((on, i) => (
          <div key={i} style={{ background: on ? "#0A0A0F" : "transparent", borderRadius: 1 }} />
        ))}
      </div>
    </div>
  );
}

function Stat({ value, label, icon, accent }: { value: string; label: string; icon: string; accent: string }) {
  return (
    <div style={{ textAlign: "center", flex: 1 }}>
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 6 }}>
        <Icon name={icon} size={16} color={accent} />
      </div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--arctic)" }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.12em", marginTop: 2 }}>
        {label}
      </div>
    </div>
  );
}

export function Profile({ slug = "black-volt" }: { slug?: string }) {
  const { t } = useI18n();
  const router = useRouter();
  const [p, setP] = useState<PublicProfile | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "missing">("loading");

  useEffect(() => {
    getPublicProfile(slug)
      .then((data) => {
        if (data) {
          setP(data);
          setState("ok");
        } else {
          setState("missing");
        }
      })
      .catch(() => setState("missing"));
  }, [slug]);

  if (state === "loading") {
    return (
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "64px 0", textAlign: "center", color: "var(--fg3)" }}>
        {t("profile.loading")}
      </div>
    );
  }
  if (state === "missing" || !p) {
    return (
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "64px 0", textAlign: "center", color: "var(--silver)" }}>
        {t("profile.notFound")}
      </div>
    );
  }

  const accent = p.brand_color || "var(--volt)";
  const subtitle = [p.name, p.city].filter(Boolean).join(" · ");

  return (
    <div
      className="bv-profile"
      style={{ maxWidth: 720, margin: "0 auto", padding: "32px 0", display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 20, alignItems: "start" }}
    >
      <Card pad={0} style={{ overflow: "hidden" }}>
        <div style={{ height: 110, position: "relative", overflow: "hidden" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={p.photo_url || "/assets/ev9-coors-field.jpg"}
            alt={p.name}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", objectPosition: "center 58%" }}
          />
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(10,10,15,0.25) 0%, rgba(10,10,15,0.92) 100%)" }} />
          <div style={{ position: "absolute", top: 16, left: 16 }}>
            <Pill icon="shield-check" tone="success">
              {t("profile.verified")}
            </Pill>
          </div>
        </div>
        <div style={{ padding: "0 22px 22px", marginTop: -34 }}>
          <div
            style={{
              width: 68,
              height: 68,
              borderRadius: "50%",
              border: `2px solid ${accent}`,
              background: "var(--obsidian-3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "var(--shadow-volt-sm)",
              marginBottom: 12,
              position: "relative",
              zIndex: 2,
              overflow: "hidden",
            }}
          >
            {p.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={p.logo_url} alt={p.name} style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            ) : (
              <Icon name="user" size={30} color="var(--silver)" />
            )}
          </div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--arctic)" }}>{p.name}</div>
          <div style={{ fontSize: 13, color: "var(--silver)", marginTop: 2 }}>{p.tagline || subtitle}</div>
          {p.bio && <div style={{ fontSize: 13, color: "var(--fg3)", marginTop: 10, lineHeight: 1.55 }}>{p.bio}</div>}
          {(p.instagram || p.website) && (
            <div style={{ display: "flex", gap: 14, marginTop: 12 }}>
              {p.instagram && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--silver)" }}>
                  <Icon name="image" size={14} color={accent} />
                  {p.instagram}
                </span>
              )}
              {p.website && (
                <a
                  href={p.website.startsWith("http") ? p.website : `https://${p.website}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--silver)", textDecoration: "none" }}
                >
                  <Icon name="globe" size={14} color={accent} />
                  {p.website.replace(/^https?:\/\//, "")}
                </a>
              )}
            </div>
          )}
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            {p.vehicle && (
              <Pill icon="car" tone="muted">
                {p.vehicle}
              </Pill>
            )}
            <Pill icon="leaf" tone="muted">
              {t("profile.electric")}
            </Pill>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 18, paddingTop: 18, borderTop: "1px solid var(--line)" }}>
            <Stat value={p.rides_total.toLocaleString()} label={t("profile.rides")} icon="navigation" accent={accent} />
            <Stat value={p.rating != null ? String(p.rating) : "—"} label={t("profile.rating")} icon="star" accent={accent} />
            <Stat value={p.years_active != null ? `${p.years_active} yr` : "—"} label={t("profile.years")} icon="clock" accent={accent} />
          </div>
          <div style={{ marginTop: 18 }}>
            <Button variant="solid" full size="lg" icon="zap" onClick={() => router.push("/book")}>
              {t("profile.book")}
            </Button>
          </div>
        </div>
      </Card>

      <Card glow pad={22} style={{ textAlign: "center" }}>
        <div style={{ display: "inline-flex", marginBottom: 16 }}>
          <Pill icon="qr-code">QR Card</Pill>
        </div>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
          <FauxQR />
        </div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 18, color: "var(--arctic)" }}>
          {t("profile.scan")}
        </div>
        <p style={{ fontSize: 13, color: "var(--silver)", margin: "8px 0 0", lineHeight: 1.5 }}>{t("profile.scan.sub")}</p>
        <div
          style={{ marginTop: 16, fontSize: 11, color: "var(--fg3)", fontFamily: "var(--font-display)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.18em" }}
        >
          blackvolt.app / d / {p.slug}
        </div>
      </Card>
    </div>
  );
}
