"use client";

import { useRouter } from "next/navigation";

import { Icon } from "../Icon";
import { Button, Card, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";

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

function Stat({ value, label, icon }: { value: string; label: string; icon: string }) {
  return (
    <div style={{ textAlign: "center", flex: 1 }}>
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 6 }}>
        <Icon name={icon} size={16} color="var(--volt)" />
      </div>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--arctic)" }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.12em", marginTop: 2 }}>
        {label}
      </div>
    </div>
  );
}

export function Profile({ slug = "ender" }: { slug?: string }) {
  const { t } = useI18n();
  const router = useRouter();
  return (
    <div
      className="bv-profile"
      style={{
        maxWidth: 720,
        margin: "0 auto",
        padding: "32px 0",
        display: "grid",
        gridTemplateColumns: "1.3fr 1fr",
        gap: 20,
        alignItems: "start",
      }}
    >
      <Card pad={0} style={{ overflow: "hidden" }}>
        <div style={{ height: 110, position: "relative", overflow: "hidden" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/assets/ev9-coors-field.jpg"
            alt="Black Kia EV9 at night in Denver"
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", objectPosition: "center 58%" }}
          />
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "linear-gradient(180deg, rgba(10,10,15,0.25) 0%, rgba(10,10,15,0.92) 100%)",
            }}
          />
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
              border: "2px solid var(--volt)",
              background: "var(--obsidian-3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "var(--shadow-volt-sm)",
              marginBottom: 12,
              position: "relative",
              zIndex: 2,
            }}
          >
            <Icon name="user" size={30} color="var(--silver)" />
          </div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--arctic)" }}>Ender</div>
          <div style={{ fontSize: 13, color: "var(--silver)", marginTop: 2 }}>Black Volt Mobility · Denver / Aurora, CO</div>
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <Pill icon="car" tone="muted">
              Kia EV9
            </Pill>
            <Pill icon="leaf" tone="muted">
              All-electric
            </Pill>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 18, paddingTop: 18, borderTop: "1px solid var(--line)" }}>
            <Stat value="1,240" label={t("profile.rides")} icon="navigation" />
            <Stat value="4.98" label={t("profile.rating")} icon="star" />
            <Stat value="3 yr" label={t("profile.years")} icon="clock" />
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
          style={{
            marginTop: 16,
            fontSize: 11,
            color: "var(--fg3)",
            fontFamily: "var(--font-display)",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.18em",
          }}
        >
          blackvolt.app / d / {slug}
        </div>
      </Card>
    </div>
  );
}
