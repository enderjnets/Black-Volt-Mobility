"use client";

/* "Share your link" — a driver's own public link + scannable QR to drop on
   Instagram, business cards, flyers. Visitors who arrive through it and sign in
   are attributed to this driver (their designated driver). */

import { useRef, useState } from "react";
import { QRCodeCanvas } from "qrcode.react";

import { Icon } from "../Icon";
import { Button } from "../ui";
import { useI18n } from "@/lib/i18n";
import { publicProfileUrl } from "@/lib/tenant";

export function ShareLink({ slug }: { slug: string }) {
  const { t } = useI18n();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const url = publicProfileUrl(slug);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked */
    }
  };

  const downloadPng = () => {
    const canvas = wrapRef.current?.querySelector("canvas");
    if (!canvas) return;
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `blackvolt-${slug}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 18 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <Icon name="qr-code" size={15} color="var(--volt)" />
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 14, color: "var(--arctic)" }}>
          {t("dash.share.title")}
        </span>
      </div>
      <p style={{ fontSize: 13, color: "var(--silver)", margin: "0 0 14px", lineHeight: 1.5 }}>
        {t("dash.share.body")}
      </p>

      <div ref={wrapRef} style={{ display: "flex", justifyContent: "center", marginBottom: 14 }}>
        <div style={{ background: "#FFFFFF", padding: 12, borderRadius: 12 }}>
          <QRCodeCanvas value={url} size={150} level="M" bgColor="#FFFFFF" fgColor="#0A0A0F" />
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          background: "var(--obsidian-3)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-md)",
          padding: "10px 12px",
          marginBottom: 12,
        }}
      >
        <Icon name="link" size={15} color="var(--silver)" />
        <span
          style={{
            flex: 1,
            fontSize: 12.5,
            color: "var(--silver)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {url.replace(/^https?:\/\//, "")}
        </span>
      </div>

      <div style={{ display: "flex", gap: 10 }}>
        <Button variant="ghost" full icon={copied ? "check" : "link"} onClick={copy}>
          {copied ? t("dash.share.copied") : t("dash.share.copy")}
        </Button>
        <Button variant="plain" full icon="upload" onClick={downloadPng}>
          {t("dash.share.download")}
        </Button>
      </div>
    </div>
  );
}
