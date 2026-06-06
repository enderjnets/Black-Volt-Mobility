"use client";

import { useRouter } from "next/navigation";

import { Icon } from "../Icon";
import { Button, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import { PUBLIC_PROFILE_SLUG } from "@/lib/tenant";

function Feature({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <div
      style={{
        background: "var(--obsidian)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-lg)",
        padding: 22,
        flex: 1,
        minWidth: 220,
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: 10,
          background: "var(--volt-bg)",
          border: "1px solid var(--volt-border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: 14,
        }}
      >
        <Icon name={icon} size={20} color="var(--volt)" />
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 600,
          fontSize: 18,
          color: "var(--arctic)",
          marginBottom: 6,
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: 14, lineHeight: 1.55, color: "var(--silver)", fontFamily: "var(--font-sans)" }}>
        {body}
      </div>
    </div>
  );
}

export function Landing() {
  const { t } = useI18n();
  const router = useRouter();
  return (
    <div>
      <section style={{ position: "relative", padding: "64px 0 56px", textAlign: "center", overflow: "hidden" }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            background: "radial-gradient(60% 50% at 50% 0%, rgba(0,229,255,0.10), transparent 70%)",
          }}
        />
        <div style={{ position: "relative" }}>
          <div style={{ display: "inline-flex", marginBottom: 24 }}>
            <Pill icon="zap">{t("brand.tagline")}</Pill>
          </div>
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 700,
              fontSize: 52,
              lineHeight: 1.05,
              color: "var(--arctic)",
              margin: "0 auto",
              maxWidth: 640,
              letterSpacing: "-0.005em",
              textWrap: "balance",
            }}
          >
            {t("home.hero.title")}
          </h1>
          <p
            style={{
              marginTop: 18,
              fontSize: 18,
              lineHeight: 1.55,
              color: "var(--silver)",
              maxWidth: 520,
              marginLeft: "auto",
              marginRight: "auto",
              fontFamily: "var(--font-sans)",
              textWrap: "pretty",
            }}
          >
            {t("home.hero.subtitle")}
          </p>
          <div style={{ marginTop: 28, display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap" }}>
            <Button variant="solid" icon="zap" size="lg" onClick={() => router.push("/book")}>
              {t("home.cta.book")}
            </Button>
            <Button variant="ghost" size="lg" iconRight="arrow-right" onClick={() => router.push(`/d/${PUBLIC_PROFILE_SLUG}`)}>
              {t("nav.driver")}
            </Button>
          </div>
        </div>
      </section>

      <section style={{ marginBottom: 56 }}>
        <div
          style={{
            position: "relative",
            borderRadius: "var(--radius-xl)",
            overflow: "hidden",
            border: "1px solid var(--line-strong)",
            boxShadow: "var(--shadow-card)",
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/assets/ev9-coors-field.jpg"
            alt="Black Kia EV9 at Coors Field, Denver, at night"
            style={{ display: "block", width: "100%", height: 420, objectFit: "cover", objectPosition: "center 60%" }}
          />
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "linear-gradient(180deg, transparent 40%, rgba(10,10,15,0.85) 100%)",
              pointerEvents: "none",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: 26,
              bottom: 22,
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <Pill icon="car">Black Kia EV9</Pill>
            <span
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 600,
                fontSize: 14,
                color: "var(--silver)",
                letterSpacing: "0.04em",
              }}
            >
              Denver · Coors Field
            </span>
          </div>
        </div>
      </section>

      <section style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 56 }}>
        <Feature icon="leaf" title={t("home.f1.t")} body={t("home.f1.d")} />
        <Feature icon="plane" title={t("home.f2.t")} body={t("home.f2.d")} />
        <Feature icon="dollar-sign" title={t("home.f3.t")} body={t("home.f3.d")} />
      </section>

      <section
        className="bv-fleet"
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 32,
          alignItems: "center",
          background: "var(--obsidian)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-xl)",
          padding: 32,
          marginBottom: 24,
        }}
      >
        <div>
          <div style={{ marginBottom: 14 }}>
            <span
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 600,
                fontSize: 12,
                textTransform: "uppercase",
                letterSpacing: "0.2em",
                color: "var(--volt)",
              }}
            >
              {t("home.fleet.eyebrow")}
            </span>
          </div>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 700,
              fontSize: 32,
              color: "var(--arctic)",
              margin: "0 0 12px",
            }}
          >
            {t("home.fleet.title")}
          </h2>
          <p style={{ fontSize: 16, lineHeight: 1.6, color: "var(--silver)", fontFamily: "var(--font-sans)", margin: 0 }}>
            {t("home.fleet.body")}
          </p>
          <div style={{ display: "flex", gap: 10, marginTop: 20, flexWrap: "wrap" }}>
            <Pill icon="users" tone="muted">
              7 seats
            </Pill>
            <Pill icon="leaf" tone="muted">
              0 emissions
            </Pill>
            <Pill icon="shield-check" tone="muted">
              Insured
            </Pill>
          </div>
        </div>
        <div style={{ borderRadius: "var(--radius-lg)", overflow: "hidden", border: "1px solid var(--line-strong)" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/assets/ev9-charging.jpg"
            alt="Black Kia EV9 charging at night"
            style={{ display: "block", width: "100%", height: 240, objectFit: "cover", objectPosition: "center 50%" }}
          />
        </div>
      </section>
    </div>
  );
}
