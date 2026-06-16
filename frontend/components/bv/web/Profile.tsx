"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { QRCodeSVG } from "qrcode.react";

import { Icon } from "../Icon";
import { Button, Card, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import {
  getPublicProfile,
  publicProfileUrl,
  PUBLIC_PROFILE_SLUG,
  type PublicProfile,
} from "@/lib/tenant";
import { fetchMe } from "@/lib/auth";
import { setRef } from "@/lib/referral";

/** Escape a value for a vCard property (RFC 6350 §3.4). */
function vcardEscape(v: string): string {
  return v.replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/,/g, "\\,").replace(/;/g, "\\;");
}

/** Trigger a .vcf download so a visitor can save the driver to their contacts. */
function saveContact(p: PublicProfile): void {
  const url = publicProfileUrl(p.slug);
  const website = p.website ? (p.website.startsWith("http") ? p.website : `https://${p.website}`) : null;
  const lines = [
    "BEGIN:VCARD",
    "VERSION:3.0",
    `FN:${vcardEscape(p.name)}`,
    `ORG:${vcardEscape(p.name)}`,
    `TITLE:${vcardEscape(p.tagline || "Black Volt Mobility")}`,
    website ? `URL:${vcardEscape(website)}` : null,
    `URL:${vcardEscape(url)}`,
    // Only present for registered viewers (the backend gates the phone field).
    p.phone ? `TEL;TYPE=CELL:${vcardEscape(p.phone)}` : null,
    p.bio ? `NOTE:${vcardEscape(p.bio)}` : null,
    "END:VCARD",
  ].filter(Boolean) as string[];
  const blob = new Blob([lines.join("\r\n")], { type: "text/vcard;charset=utf-8" });
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = `${p.slug}.vcf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
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

export function Profile({ slug = PUBLIC_PROFILE_SLUG }: { slug?: string }) {
  const { t } = useI18n();
  const router = useRouter();
  const [p, setP] = useState<PublicProfile | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "missing">("loading");
  const [isMine, setIsMine] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    // Capture the referral: a visitor on a driver's link is attributed to that
    // driver on their next sign-in (the backend enforces first-touch permanence).
    setRef(slug);
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
    // Is this the signed-in passenger's own designated driver?
    fetchMe()
      .then((me) => setIsMine(me.authenticated && me.tenant_slug === slug))
      .catch(() => setIsMine(false));
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
      <div style={{ maxWidth: 460, margin: "0 auto", padding: "72px 20px", textAlign: "center" }}>
        <div
          style={{
            display: "inline-flex",
            width: 56,
            height: 56,
            borderRadius: 14,
            background: "var(--obsidian-3)",
            border: "1px solid var(--line-strong)",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: 16,
          }}
        >
          <Icon name="user" size={26} color="var(--silver)" />
        </div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, color: "var(--arctic)", marginBottom: 18 }}>
          {t("profile.notFound")}
        </div>
        <Button variant="solid" size="lg" icon="zap" onClick={() => router.push("/book")}>
          {t("profile.book")}
        </Button>
      </div>
    );
  }

  const accent = p.brand_color || "var(--volt)";
  const subtitle = [p.name, p.city].filter(Boolean).join(" · ");
  const shareUrl = publicProfileUrl(p.slug);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked — no-op */
    }
  };

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
          <div style={{ position: "absolute", top: 16, left: 16, display: "flex", gap: 8 }}>
            <Pill icon="shield-check" tone="success">
              {t("profile.verified")}
            </Pill>
            {isMine && (
              <Pill icon="star" tone="volt">
                {t("profile.yourDriver")}
              </Pill>
            )}
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
                <a
                  href={`https://instagram.com/${p.instagram.replace(/^@/, "")}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--silver)", textDecoration: "none" }}
                >
                  <Icon name="image" size={14} color={accent} />
                  {p.instagram}
                </a>
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
          {/* Direct line — only delivered by the backend to registered/signed-in
              clients, so its mere presence means the viewer is entitled to it. */}
          {p.phone && (
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <Button variant="ghost" icon="phone" onClick={() => { window.location.href = `tel:${p.phone}`; }}>
                {t("profile.call")}
              </Button>
              <Button variant="plain" icon="message-circle" onClick={() => { window.location.href = `sms:${p.phone}`; }}>
                {t("profile.text")}
              </Button>
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
          <Pill icon="qr-code">{t("profile.qrCard")}</Pill>
        </div>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
          <div style={{ background: "var(--arctic)", padding: 12, borderRadius: 12 }}>
            <QRCodeSVG value={shareUrl} size={140} level="M" bgColor="#FFFFFF" fgColor="#0A0A0F" />
          </div>
        </div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 18, color: "var(--arctic)" }}>
          {t("profile.scan")}
        </div>
        <p style={{ fontSize: 13, color: "var(--silver)", margin: "8px 0 16px", lineHeight: 1.5 }}>{t("profile.scan.sub")}</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <Button variant="ghost" full icon="user" onClick={() => saveContact(p)}>
            {t("profile.saveContact")}
          </Button>
          <Button variant="plain" full icon={copied ? "check" : "link"} onClick={copyLink}>
            {copied ? t("profile.copied") : t("profile.copyLink")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
