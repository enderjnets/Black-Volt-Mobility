"use client";

import { useEffect, useState } from "react";

import { Markdown } from "@/components/bv/Markdown";
import { useI18n } from "@/lib/i18n";

interface Doc {
  title: string;
  content_md: string;
  version: string;
  lang: string;
}

/* Public legal-document page (/terms, /privacy). Fetches the versioned document
   from the public backend endpoint in the current UI language and renders it with
   the shared Markdown component. No auth — usable by anyone, including from the
   links inside the agreements themselves. */
export function LegalDocPage({ docType }: { docType: string }) {
  const { lang, setLang } = useI18n();
  const [doc, setDoc] = useState<Doc | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setDoc(null);
    setError(false);
    fetch(`/api/v1/agreements/public/${docType}?lang=${lang}`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((d) => {
        if (active) setDoc(d);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [docType, lang]);

  return (
    <main
      style={{
        minHeight: "100dvh",
        background: "var(--void, #0A0A0F)",
        padding: "32px 16px 64px",
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div style={{ width: "100%", maxWidth: 760 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 24,
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <a
            href="/"
            style={{
              color: "var(--volt, #00E5FF)",
              textDecoration: "none",
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            ← Black Volt Mobility
          </a>
          <div style={{ display: "flex", gap: 6 }}>
            {(["en", "es"] as const).map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => setLang(l)}
                style={{
                  background: l === lang ? "var(--volt, #00E5FF)" : "transparent",
                  color: l === lang ? "#0A0A0F" : "var(--silver, #9AA4B2)",
                  border: "1px solid var(--volt, #00E5FF)",
                  borderRadius: 6,
                  padding: "4px 12px",
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: "pointer",
                  textTransform: "uppercase",
                }}
              >
                {l}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <p style={{ color: "var(--silver, #9AA4B2)" }}>
            {lang === "es" ? "No se pudo cargar el documento." : "Could not load the document."}
          </p>
        )}
        {!doc && !error && (
          <p style={{ color: "var(--silver, #9AA4B2)" }}>
            {lang === "es" ? "Cargando…" : "Loading…"}
          </p>
        )}
        {doc && (
          <article>
            <Markdown content={doc.content_md} />
            <p style={{ marginTop: 32, color: "var(--steel, #667085)", fontSize: 12 }}>
              v{doc.version}
            </p>
          </article>
        )}
      </div>
    </main>
  );
}
