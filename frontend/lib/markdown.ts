/**
 * Minimal, XSS-safe Markdown → HTML for Volt Blog articles.
 *
 * The content is our OWN backend-generated markdown (grounded LLM output, internal links
 * already validated server-side), so a small dependency-free renderer is enough. Everything
 * is HTML-escaped first, so even if the model emitted raw HTML it renders as text, never
 * executes. Links are only honored when the href is an internal path ("/..."); anything else
 * degrades to plain text. Supports: ## / ### headings, paragraphs, **bold**, *italic*,
 * `code`, unordered lists, and internal [text](/path) links.
 */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Inline transforms applied to already-escaped text. */
function inline(escaped: string): string {
  let out = escaped;
  // Internal links only: [text](/path). External/`javascript:` hrefs fall through to text.
  out = out.replace(/\[([^\]]+)\]\((\/[^\s)]*)\)/g, (_m, text, href) => {
    return `<a href="${href}">${text}</a>`;
  });
  // Any remaining [text](...) that wasn't an internal link → keep just the text.
  out = out.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  return out;
}

export function renderMarkdown(md: string | null | undefined): string {
  if (!md) return "";
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let para: string[] = [];
  let list: string[] = [];

  const flushPara = () => {
    if (para.length) {
      html.push(`<p>${inline(escapeHtml(para.join(" ").trim()))}</p>`);
      para = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      html.push(`<ul>${list.map((li) => `<li>${inline(escapeHtml(li))}</li>`).join("")}</ul>`);
      list = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flushPara();
      flushList();
      continue;
    }
    const h3 = line.match(/^###\s+(.*)$/);
    const h2 = line.match(/^##\s+(.*)$/);
    const h1 = line.match(/^#\s+(.*)$/);
    const li = line.match(/^[-*]\s+(.*)$/);
    if (h3) {
      flushPara();
      flushList();
      html.push(`<h3>${inline(escapeHtml(h3[1].trim()))}</h3>`);
    } else if (h2) {
      flushPara();
      flushList();
      html.push(`<h2>${inline(escapeHtml(h2[1].trim()))}</h2>`);
    } else if (h1) {
      flushPara();
      flushList();
      html.push(`<h2>${inline(escapeHtml(h1[1].trim()))}</h2>`);
    } else if (li) {
      flushPara();
      list.push(li[1].trim());
    } else {
      flushList();
      para.push(line.trim());
    }
  }
  flushPara();
  flushList();
  return html.join("\n");
}
