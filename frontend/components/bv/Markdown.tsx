/* Tiny, safe, dependency-free markdown renderer (no dangerouslySetInnerHTML).
   Handles #/##/### headings, paragraphs, "- " bullets, **bold**, and blank-line
   breaks. Extracted from AgreementGate so the public /terms and /privacy pages
   render legal docs with identical, brand-consistent styling. React elements only. */

import { Fragment, type ReactNode } from "react";

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

export function renderMarkdown(md: string): ReactNode[] {
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

export function Markdown({ content }: { content: string }) {
  return <>{renderMarkdown(content)}</>;
}
