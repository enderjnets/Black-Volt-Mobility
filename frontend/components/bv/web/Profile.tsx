"use client";

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import { Icon } from "../Icon";
import { Button, Card, Pill } from "../ui";
import ReviewsStrip from "./ReviewsStrip";
import { useI18n } from "@/lib/i18n";
import {
  getPublicProfile,
  publicProfileUrl,
  publicSiteOrigin,
  instagramUrl,
  websiteUrl,
  PUBLIC_PROFILE_SLUG,
  type PublicProfile,
} from "@/lib/tenant";
import { fetchMe } from "@/lib/auth";
import { setRef } from "@/lib/referral";

/** Escape a value for a vCard property (RFC 6350 §3.4). */
function vcardEscape(v: string): string {
  return v
    .replace(/\\/g, "\\\\")
    .replace(/\r\n|\r|\n/g, "\\n")
    .replace(/,/g, "\\,")
    .replace(/;/g, "\\;");
}

/** RFC 2426 line folding: ≤75 octets per line, continuation lines begin with a
 * space. Needed so the (long) base64 PHOTO line imports on stricter clients (iOS). */
function foldVcard(line: string): string {
  if (line.length <= 75) return line;
  const parts: string[] = [line.slice(0, 75)];
  let rest = line.slice(75);
  while (rest.length > 74) {
    parts.push(" " + rest.slice(0, 74));
    rest = rest.slice(74);
  }
  parts.push(" " + rest);
  return parts.join("\r\n");
}

/** Build a vCard PHOTO line for the driver avatar: base64-embedded so it shows in
 * Contacts offline, falling back to a URI reference if the image can't be fetched
 * (CORS/network), or null when there's no photo. */
async function vcardPhotoLine(rawUrl: string | null | undefined): Promise<string | null> {
  if (!rawUrl) return null;
  const abs = rawUrl.startsWith("http")
    ? rawUrl
    : `${publicSiteOrigin()}${rawUrl.startsWith("/") ? "" : "/"}${rawUrl}`;
  try {
    const res = await fetch(abs, { mode: "cors" });
    if (!res.ok) throw new Error(String(res.status));
    const blob = await res.blob();
    const dataUrl: string = await new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result));
      fr.onerror = () => reject(fr.error);
      fr.readAsDataURL(blob);
    });
    const m = dataUrl.match(/^data:(image\/[a-z0-9.+-]+);base64,(.+)$/i);
    if (!m) throw new Error("not-image");
    const type = m[1].split("/")[1].toUpperCase();
    return foldVcard(`PHOTO;ENCODING=b;TYPE=${type}:${m[2]}`);
  } catch {
    return `PHOTO;VALUE=URI:${vcardEscape(abs)}`;
  }
}

/** Send the customer to the PUBLIC booking page on the apex host (never the
 * dashboard `app.` subdomain), carrying the driver referral so the funnel
 * attributes the lead and prices against that driver's rate even across the host
 * boundary (the referral cookie is host-scoped, so the `?ref=` param carries it). */
function gotoBook(slug?: string): void {
  const base = `${publicSiteOrigin()}/book`;
  window.location.assign(slug ? `${base}?ref=${encodeURIComponent(slug)}` : base);
}

/** Trigger a .vcf download so a visitor can save the driver to their contacts —
 * complete info (name, org, title, phone, profile + website + Instagram links,
 * bio) plus the embedded avatar photo. */
async function saveContact(p: PublicProfile): Promise<void> {
  const nameParts = p.name.trim().split(/\s+/);
  const given = nameParts[0] || p.name;
  const family = nameParts.slice(1).join(" ");
  const profileUrl = publicProfileUrl(p.slug);
  const site = websiteUrl(p.website);
  const ig = instagramUrl(p.instagram);
  const photo = await vcardPhotoLine(p.logo_url);
  const lines = [
    "BEGIN:VCARD",
    "VERSION:3.0",
    `N:${vcardEscape(family)};${vcardEscape(given)};;;`,
    `FN:${vcardEscape(p.name)}`,
    "ORG:Black Volt Mobility",
    `TITLE:${vcardEscape(p.tagline || "Black Volt Mobility")}`,
    photo,
    // Only present for registered viewers (the backend gates the phone field).
    p.phone ? `TEL;TYPE=CELL,VOICE:${vcardEscape(p.phone)}` : null,
    `URL:${vcardEscape(profileUrl)}`,
    site ? `URL:${vcardEscape(site)}` : null,
    ig ? `X-SOCIALPROFILE;TYPE=instagram:${vcardEscape(ig)}` : null,
    ig ? `URL:${vcardEscape(ig)}` : null,
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

/** Modern pill link (icon + label) for a driver's social/web links. Replaces the
 * raw URL text so a broken/overflowing link can't render — and the symbol reads
 * professionally at a glance. */
function SocialPill({ href, icon, label, accent }: { href: string; icon: string; label: string; accent: string }) {
  const [h, setH] = useState(false);
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 14px",
        borderRadius: 999,
        border: `1px solid ${h ? accent : "var(--line-strong)"}`,
        background: "var(--obsidian-3)",
        color: h ? "var(--arctic)" : "var(--silver)",
        fontSize: 13,
        fontWeight: 600,
        fontFamily: "var(--font-sans)",
        textDecoration: "none",
        boxShadow: h ? `0 0 0 1px ${accent}33, 0 6px 18px -8px ${accent}` : "none",
        transition: "all .15s",
      }}
    >
      <Icon name={icon} size={16} color={accent} />
      {label}
    </a>
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

export function Profile({ slug = PUBLIC_PROFILE_SLUG }: { slug?: string }) {
  const { t } = useI18n();
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
        <Button variant="solid" size="lg" icon="zap" onClick={() => gotoBook()}>
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
            src={p.photo_url || "/assets/ev9-coors-field-800w.webp"}
            loading="lazy"
            decoding="async"
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
          {(() => {
            const ig = instagramUrl(p.instagram);
            const site = websiteUrl(p.website);
            if (!ig && !site) return null;
            return (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 14 }}>
                {ig && (
                  <SocialPill href={ig} icon="instagram" label={t("profile.instagram")} accent={accent} />
                )}
                {site && (
                  <SocialPill href={site} icon="globe" label={t("profile.website")} accent={accent} />
                )}
              </div>
            );
          })()}
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
            <Button variant="solid" full size="lg" icon="zap" onClick={() => gotoBook(p.slug)}>
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
          <Button variant="ghost" full icon="user" onClick={() => void saveContact(p)}>
            {t("profile.saveContact")}
          </Button>
          <Button variant="plain" full icon={copied ? "check" : "link"} onClick={copyLink}>
            {copied ? t("profile.copied") : t("profile.copyLink")}
          </Button>
        </div>
      </Card>

      <ReviewsStrip surface="profile" limit={6} />
      <a
        href={`/review?driver=${encodeURIComponent(p.slug)}`}
        style={{
          display: "inline-block",
          marginTop: 16,
          fontSize: 13.5,
          fontWeight: 600,
          color: "var(--volt)",
          textDecoration: "none",
        }}
      >
        ★ {t("reviews.cta.write")}
      </a>
    </div>
  );
}
