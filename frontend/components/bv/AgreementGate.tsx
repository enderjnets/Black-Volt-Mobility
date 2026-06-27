/* Mandatory legal-agreement signing gate. Non-dismissable, mobile-first full-screen
   overlay shown when /auth/me returns a non-empty `agreements_pending`. Works through
   the pending docs one at a time. Passengers (client_terms) get a clickwrap checkbox;
   drivers (driver_agreement) must also type their full legal name as an e-signature.
   Mirrors the overlay styling of web/ProfileGate.tsx so it stays brand-consistent. */
"use client";

import { Fragment, type ReactNode, useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { getAgreement, acceptAgreement, type Agreement } from "@/lib/agreements";
import { Button, Logo } from "./ui";
import { Icon } from "./Icon";

/* ---- tiny, safe markdown renderer (no deps, no dangerouslySetInnerHTML) ---- */

function renderInline(text: string, keyBase: string): ReactNode[] {
  // Split on **bold** spans, keeping the captured groups.
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts
    .filter((p) => p.length > 0)
    .map((p, i) => {
      if (p.startsWith("**") && p.endsWith("**") && p.length > 4) {
        return (
          <strong key={`${keyBase}-b${i}`} style={{ color: "var(--arctic)", fontWeight: 700 }}>
            {p.slice(2, -2)}
          </strong>
        );
      }
      return <Fragment key={`${keyBase}-t${i}`}>{p}</Fragment>;
    });
}

function renderMarkdown(md: string): ReactNode[] {
  const blocks = md.replace(/\r\n/g, "\n").split(/\n{2,}/);
  const out: ReactNode[] = [];
  blocks.forEach((raw, bi) => {
    const block = raw.trim();
    if (!block) return;
    const lines = block.split("\n");

    // Bullet list: every line starts with "- ".
    if (lines.every((l) => l.trim().startsWith("- "))) {
      out.push(
        <ul
          key={`b${bi}`}
          style={{ margin: "0 0 14px", paddingLeft: 20, color: "var(--silver)", lineHeight: 1.6 }}
        >
          {lines.map((l, li) => (
            <li key={`b${bi}-${li}`} style={{ marginBottom: 6 }}>
              {renderInline(l.trim().slice(2), `b${bi}-${li}`)}
            </li>
          ))}
        </ul>,
      );
      return;
    }

    // Headings (single-line blocks).
    if (lines.length === 1) {
      const l = lines[0];
      if (l.startsWith("### ")) {
        out.push(
          <h3 key={`b${bi}`} style={{ margin: "14px 0 6px", fontFamily: "var(--font-display)", fontSize: 15, color: "var(--arctic)" }}>
            {renderInline(l.slice(4), `b${bi}`)}
          </h3>,
        );
        return;
      }
      if (l.startsWith("## ")) {
        out.push(
          <h2 key={`b${bi}`} style={{ margin: "16px 0 8px", fontFamily: "var(--font-display)", fontSize: 17, color: "var(--arctic)" }}>
            {renderInline(l.slice(3), `b${bi}`)}
          </h2>,
        );
        return;
      }
      if (l.startsWith("# ")) {
        out.push(
          <h1 key={`b${bi}`} style={{ margin: "8px 0 10px", fontFamily: "var(--font-display)", fontSize: 20, color: "var(--arctic)" }}>
            {renderInline(l.slice(2), `b${bi}`)}
          </h1>,
        );
        return;
      }
    }

    // Paragraph (join wrapped lines with spaces).
    out.push(
      <p key={`b${bi}`} style={{ margin: "0 0 12px", color: "var(--silver)", lineHeight: 1.65, fontSize: 14 }}>
        {renderInline(lines.join(" "), `b${bi}`)}
      </p>,
    );
  });
  return out;
}

export function AgreementGate({ pending, onComplete }: { pending: string[]; onComplete: () => void }) {
  const { t, lang } = useI18n();
  const [idx, setIdx] = useState(0);
  const [doc, setDoc] = useState<Agreement | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [versionChanged, setVersionChanged] = useState(false);
  const [checked, setChecked] = useState(false);
  const [signedName, setSignedName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const docType = pending[idx];
  const isDriver = docType === "driver_agreement";

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setChecked(false);
    setSignedName("");
    getAgreement(docType, lang)
      .then((d) => {
        if (!alive) return;
        setDoc(d);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : "error");
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [docType, lang, reloadKey]);

  const canAccept = checked && (!isDriver || signedName.trim().length > 0) && !submitting && !!doc;

  async function onAccept() {
    if (!doc || !canAccept) return;
    setSubmitting(true);
    setError(null);
    try {
      await acceptAgreement(docType, {
        version: doc.version,
        lang,
        signedName: isDriver ? signedName.trim() : undefined,
      });
      if (idx + 1 < pending.length) {
        setVersionChanged(false);
        setIdx(idx + 1);
      } else {
        onComplete();
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes(":409")) {
        // Version changed under us — re-fetch the latest doc and re-prompt.
        setVersionChanged(true);
        setReloadKey((k) => k + 1);
      } else {
        setError("generic");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("agreement.title")}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1100,
        background: "rgba(5,5,9,0.92)",
        backdropFilter: "blur(4px)",
        display: "flex",
        justifyContent: "center",
        alignItems: "stretch",
        padding: "16px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 560,
          margin: "auto",
          maxHeight: "calc(100dvh - 32px)",
          display: "flex",
          flexDirection: "column",
          background: "var(--obsidian)",
          border: "1px solid var(--volt-border)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-volt)",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div style={{ padding: "20px 22px 14px", borderBottom: "1px solid var(--line)" }}>
          <div style={{ marginBottom: 12 }}>
            <Logo size={18} />
          </div>
          <h2
            style={{
              margin: 0,
              fontFamily: "var(--font-display)",
              fontSize: 21,
              color: "var(--arctic)",
            }}
          >
            {doc?.title || t("agreement.title")}
          </h2>
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--fg3)", fontFamily: "var(--font-sans)" }}>
            {t("agreement.intro")}
          </p>
        </div>

        {/* Scrollable document body */}
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
            padding: "18px 22px",
            background: "var(--obsidian-2)",
            fontFamily: "var(--font-sans)",
          }}
        >
          {loading ? (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 10,
                padding: "40px 0",
                color: "var(--silver)",
              }}
            >
              <Icon name="zap" size={20} color="var(--volt)" fill="var(--volt)" />
              {t("agreement.loading")}
            </div>
          ) : doc ? (
            renderMarkdown(doc.content_md)
          ) : (
            <p style={{ color: "var(--silver)" }}>{t("agreement.error")}</p>
          )}
        </div>

        {/* Footer / actions */}
        <div style={{ padding: "16px 22px 18px", borderTop: "1px solid var(--line)" }}>
          {versionChanged && (
            <div
              style={{
                fontSize: 12.5,
                color: "var(--warning)",
                marginBottom: 12,
                lineHeight: 1.5,
              }}
            >
              {t("agreement.versionChanged")}
            </div>
          )}

          <label
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              cursor: "pointer",
              marginBottom: isDriver ? 14 : 16,
            }}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
              style={{ width: 18, height: 18, marginTop: 1, accentColor: "var(--volt)", flexShrink: 0 }}
            />
            <span style={{ fontSize: 13.5, color: "var(--silver)", lineHeight: 1.5, fontFamily: "var(--font-sans)" }}>
              {t("agreement.readAndAccept")}
            </span>
          </label>

          {isDriver && (
            <label style={{ display: "block", marginBottom: 16 }}>
              <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7, fontFamily: "var(--font-sans)" }}>
                {t("agreement.fullNameLabel")}
              </div>
              <input
                type="text"
                value={signedName}
                onChange={(e) => setSignedName(e.target.value)}
                placeholder={t("agreement.fullNamePlaceholder")}
                autoComplete="name"
                style={{
                  width: "100%",
                  background: "var(--obsidian-3)",
                  border: "1px solid var(--line-strong)",
                  borderRadius: "var(--radius-md)",
                  padding: "12px 14px",
                  color: "var(--arctic)",
                  fontSize: 14,
                  fontFamily: "var(--font-sans)",
                  outline: "none",
                }}
              />
            </label>
          )}

          {error && (
            <div style={{ fontSize: 12.5, color: "var(--danger, #ff5a5a)", marginBottom: 12 }}>
              {t("agreement.error")}
            </div>
          )}

          <Button variant="solid" full disabled={!canAccept} onClick={onAccept}>
            {isDriver ? t("agreement.acceptSignBtn") : t("agreement.acceptBtn")}
          </Button>
        </div>
      </div>
    </div>
  );
}
