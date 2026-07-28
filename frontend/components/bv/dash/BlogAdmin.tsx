"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Card, Field, Pill, Toggle } from "@/components/bv/ui";
import { useI18n } from "@/lib/i18n";
import {
  addBlogKeyword,
  autofillBlogConfig,
  discoverBlogKeywords,
  generateBlogPostAndWait,
  getBlogAnalytics,
  getBlogConfig,
  gscAuthorizeUrl,
  listBlogKeywords,
  listBlogPosts,
  patchBlogPost,
  publishBlogPost,
  putBlogConfig,
  runBlogSpeed,
  setBlogKeywordStatus,
  setBlogPostStatus,
  type BlogAnalyticsT,
  type BlogConfigT,
  type BlogKeywordT,
  type BlogPostT,
  type BlogSpeedPageT,
} from "@/lib/blogAdmin";

type Tab = "calendar" | "posts" | "keywords" | "brand" | "analytics" | "speed";

const TABS: { id: Tab; key: string }[] = [
  { id: "calendar", key: "blog.tab.calendar" },
  { id: "posts", key: "blog.tab.posts" },
  { id: "keywords", key: "blog.tab.keywords" },
  { id: "brand", key: "blog.tab.brand" },
  { id: "analytics", key: "blog.tab.analytics" },
  { id: "speed", key: "blog.tab.speed" },
];

function fmtWhen(iso: string | null, lang: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(lang === "es" ? "es-US" : "en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: "America/Denver",
    });
  } catch {
    return "—";
  }
}

function countdown(iso: string | null): string {
  if (!iso) return "";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "due";
  const h = Math.floor(ms / 3.6e6);
  const m = Math.floor((ms % 3.6e6) / 6e4);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function statusTone(s: string): "volt" | "success" | "warning" | "muted" {
  if (s === "published") return "success";
  if (s === "scheduled") return "volt";
  if (s === "failed" || s === "vetoed" || s === "archived" || s === "draft") return "warning";
  return "muted";
}

export function BlogAdmin() {
  const { t, lang } = useI18n();
  const [tab, setTab] = useState<Tab>("calendar");
  const [config, setConfig] = useState<BlogConfigT | null>(null);
  const [posts, setPosts] = useState<BlogPostT[]>([]);
  const [keywords, setKeywords] = useState<BlogKeywordT[]>([]);
  const [analytics, setAnalytics] = useState<BlogAnalyticsT | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const reloadPosts = useCallback(async () => {
    try {
      setPosts(await listBlogPosts());
    } catch {
      /* not admin / offline */
    }
  }, []);
  const reloadKeywords = useCallback(async () => {
    try {
      setKeywords(await listBlogKeywords());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    getBlogConfig().then(setConfig).catch(() => {});
    reloadPosts();
    reloadKeywords();
    // Flash the outcome of a returning GSC OAuth redirect (?gsc=connected|error|noretoken).
    if (typeof window !== "undefined") {
      const g = new URLSearchParams(window.location.search).get("gsc");
      if (g) {
        setMsg(g === "connected" ? t("blog.msg.gscConnected") : t("blog.msg.gscError"));
        setTimeout(() => setMsg(null), 4000);
        window.history.replaceState({}, "", "/dashboard/blog");
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadPosts, reloadKeywords]);

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(null), 3000);
  };
  /** Writing takes a couple of minutes, so the message has to keep talking or it reads as
   *  a hang. The status pill on the finished card says whether it passed. */
  const write = async (opts: { keyword_id?: number; keyword?: string }) => {
    setMsg(t("blog.msg.writing"));
    const fresh = await generateBlogPostAndWait(opts, (secs) =>
      setMsg(t("blog.msg.writingSecs", { secs })),
    );
    setPosts(fresh);
    flash(
      fresh[0]?.status === "draft" ? t("blog.msg.drafted") : t("blog.msg.generated"),
    );
  };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // Drafts belong here too: they are the ones asking for a decision, so burying them in
  // another tab would defeat the point of holding them back.
  const scheduled = posts.filter(
    (p) => p.status === "scheduled" || p.status === "generating" || p.status === "draft",
  );
  const published = posts.filter((p) => p.status === "published");

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "8px 4px 40px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 800, color: "var(--arctic)", margin: "0 0 4px" }}>
        {t("blog.admin.title")}
      </h1>
      <p style={{ color: "var(--fg3)", fontSize: 13, margin: "0 0 14px" }}>{t("blog.subtitle")}</p>

      {msg ? (
        <div style={{ marginBottom: 12, padding: "8px 12px", borderRadius: 8, background: "var(--obsidian)", color: "var(--arctic)", fontSize: 13 }}>
          {msg}
        </div>
      ) : null}

      {/* Sub-tab pills */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        {TABS.map((tb) => {
          const active = tb.id === tab;
          const count =
            tb.id === "calendar" ? scheduled.length : tb.id === "posts" ? published.length : tb.id === "keywords" ? keywords.length : undefined;
          return (
            <button
              key={tb.id}
              onClick={() => setTab(tb.id)}
              style={{
                padding: "7px 12px",
                borderRadius: 99,
                border: "none",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                background: active ? "var(--volt-bg-20, rgba(0,229,255,0.14))" : "var(--obsidian)",
                color: active ? "var(--volt)" : "var(--fg2)",
              }}
            >
              {t(tb.key)}
              {count !== undefined ? ` (${count})` : ""}
            </button>
          );
        })}
      </div>

      {tab === "calendar" && (
        <CalendarTab
          scheduled={scheduled}
          lang={lang}
          busy={busy}
          onGenerate={() => run(async () => { await write({}); })}
          onPublish={(id) => run(async () => { await publishBlogPost(id); await reloadPosts(); flash(t("blog.msg.published")); })}
          onVeto={(id) => run(async () => { await setBlogPostStatus(id, "archived"); await reloadPosts(); })}
          onSave={(id, patch) => run(async () => { await patchBlogPost(id, patch); await reloadPosts(); flash(t("blog.msg.saved")); })}
          t={t}
        />
      )}

      {tab === "posts" && (
        <PostsTab published={published} lang={lang} t={t}
          onArchive={(id) => run(async () => { await setBlogPostStatus(id, "archived"); await reloadPosts(); })}
        />
      )}

      {tab === "keywords" && (
        <KeywordsTab
          keywords={keywords}
          busy={busy}
          t={t}
          onDiscover={() => run(async () => { const r = await discoverBlogKeywords(); await reloadKeywords(); flash(r.skipped ? r.skipped : t("blog.msg.discovered", { found: r.found ?? 0, promoted: r.promoted ?? 0 })); })}
          onAdd={(kw, lg) => run(async () => { await addBlogKeyword(kw, lg); await reloadKeywords(); })}
          onStatus={(id, s) => run(async () => { await setBlogKeywordStatus(id, s); await reloadKeywords(); })}
          onWrite={(id) => run(async () => { await write({ keyword_id: id }); await reloadKeywords(); })}
        />
      )}

      {tab === "brand" && config && (
        <BrandTab
          key={`${config.voice ?? ""}|${(config.key_themes || []).join(",")}|${(config.avoid_topics || []).join(",")}`}
          config={config} busy={busy} t={t}
          onSave={(patch) => run(async () => { const c = await putBlogConfig(patch); setConfig(c); flash(t("blog.msg.saved")); })}
          onAutofill={() => run(async () => { const c = await autofillBlogConfig(); setConfig(c); flash(t("blog.msg.autofilled")); })}
        />
      )}

      {tab === "analytics" && (
        <AnalyticsTab analytics={analytics} config={config} busy={busy} t={t}
          onLoad={() => run(async () => { setAnalytics(await getBlogAnalytics()); })}
          onConnect={(siteUrl) => run(async () => { const { url } = await gscAuthorizeUrl(siteUrl); window.location.href = url; })}
        />
      )}

      {tab === "speed" && (
        <SpeedTab analytics={analytics} busy={busy} t={t}
          onLoad={() => run(async () => { setAnalytics(await getBlogAnalytics()); })}
          onRun={() => run(async () => { const r = await runBlogSpeed(); setAnalytics(await getBlogAnalytics()); flash(t("blog.speed.done", { pages: r.pages ?? 0, warnings: r.warnings ?? 0 })); })}
        />
      )}
    </div>
  );
}

// ─── Calendar (scheduled, hybrid-24h window) ─────────────────────────────────────

function CalendarTab({ scheduled, lang, busy, onGenerate, onPublish, onVeto, onSave, t }: {
  scheduled: BlogPostT[]; lang: string; busy: boolean;
  onGenerate: () => void; onPublish: (id: number) => void; onVeto: (id: number) => void;
  onSave: (id: number, patch: Partial<BlogPostT>) => void;
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <Button onClick={onGenerate} disabled={busy}>{t("blog.action.generate")}</Button>
      {scheduled.length === 0 ? (
        <p style={{ color: "var(--fg3)", fontSize: 13 }}>{t("blog.empty.calendar")}</p>
      ) : (
        scheduled.map((p) => (
          <Card key={p.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, color: "var(--arctic)", fontSize: 15 }}>{p.title_en}</div>
                <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 3 }}>
                  {p.status === "draft"
                    ? t("blog.field.heldBack")
                    : `${t("blog.field.publishes")}: ${fmtWhen(p.publish_at, lang)} · ${countdown(p.publish_at)}`}
                </div>
              </div>
              <Pill tone={statusTone(p.status)}>{p.status}</Pill>
            </div>
            {p.status === "draft" && <QualityIssues post={p} t={t} />}
            <EditRow post={p} onSave={onSave} t={t} />
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <Button onClick={() => onPublish(p.id)} disabled={busy}>{t("blog.action.publishNow")}</Button>
              <Button variant="ghost" onClick={() => onVeto(p.id)} disabled={busy}>{t("blog.action.veto")}</Button>
            </div>
          </Card>
        ))
      )}
    </div>
  );
}

function QualityIssues({ post, t }: {
  post: BlogPostT;
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  const langs = Object.keys(post.quality_issues || {});
  if (langs.length === 0) return null;
  return (
    <div style={{
      marginTop: 8, padding: "8px 10px", borderRadius: 8,
      background: "var(--obsidian-3,#15151c)", border: "1px solid var(--line,#23232b)",
    }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--danger,#ff5c5c)" }}>
        {t("blog.quality.title")}
      </div>
      {langs.map((lg) => (
        <div key={lg} style={{ marginTop: 6 }}>
          <div style={{ fontSize: 11, color: "var(--fg3)", textTransform: "uppercase" }}>{lg}</div>
          <ul style={{ margin: "2px 0 0", paddingLeft: 16 }}>
            {(post.quality_issues[lg] || []).map((issue, i) => (
              <li key={i} style={{ fontSize: 12, color: "var(--silver,#c9c9d1)", lineHeight: 1.45 }}>
                {issue}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function EditRow({ post, onSave, t }: {
  post: BlogPostT; onSave: (id: number, patch: Partial<BlogPostT>) => void;
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  const [open, setOpen] = useState(false);
  const [titleEn, setTitleEn] = useState(post.title_en);
  const [bodyEn, setBodyEn] = useState(post.body_md_en || "");
  const [titleEs, setTitleEs] = useState(post.title_es || "");
  const [bodyEs, setBodyEs] = useState(post.body_md_es || "");
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={{ marginTop: 8, background: "none", border: "none", color: "var(--volt)", cursor: "pointer", fontSize: 12, padding: 0 }}>
        {t("blog.action.edit")} ▾
      </button>
    );
  }
  return (
    <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
      <Field label={t("blog.field.titleEn")} value={titleEn} onChange={setTitleEn} />
      <label style={{ fontSize: 12, color: "var(--fg3)" }}>{t("blog.field.bodyEn")}</label>
      <textarea value={bodyEn} onChange={(e) => setBodyEn(e.target.value)} rows={8}
        style={{ width: "100%", background: "var(--void)", color: "var(--arctic)", border: "1px solid var(--hairline,#23232b)", borderRadius: 8, padding: 10, fontSize: 13, fontFamily: "inherit" }} />
      <Field label={t("blog.field.titleEs")} value={titleEs} onChange={setTitleEs} />
      <label style={{ fontSize: 12, color: "var(--fg3)" }}>{t("blog.field.bodyEs")}</label>
      <textarea value={bodyEs} onChange={(e) => setBodyEs(e.target.value)} rows={8}
        style={{ width: "100%", background: "var(--void)", color: "var(--arctic)", border: "1px solid var(--hairline,#23232b)", borderRadius: 8, padding: 10, fontSize: 13, fontFamily: "inherit" }} />
      <div style={{ display: "flex", gap: 8 }}>
        <Button onClick={() => { onSave(post.id, { title_en: titleEn, body_md_en: bodyEn, title_es: titleEs, body_md_es: bodyEs }); setOpen(false); }}>
          {t("blog.action.save")}
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>{t("blog.action.cancel")}</Button>
      </div>
    </div>
  );
}

// ─── Posts (published) ───────────────────────────────────────────────────────────

function PostsTab({ published, lang, t, onArchive }: {
  published: BlogPostT[]; lang: string;
  t: (k: string, v?: Record<string, string | number>) => string;
  onArchive: (id: number) => void;
}) {
  if (published.length === 0) return <p style={{ color: "var(--fg3)", fontSize: 13 }}>{t("blog.empty.posts")}</p>;
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {published.map((p) => (
        <Card key={p.id}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
            <div>
              <a href={`/blog/${p.slug}`} target="_blank" rel="noreferrer" style={{ fontWeight: 700, color: "var(--arctic)", fontSize: 15 }}>
                {p.title_en}
              </a>
              <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 3 }}>{fmtWhen(p.published_at, lang)} · /blog/{p.slug}</div>
            </div>
            <Pill tone="success">{p.status}</Pill>
          </div>
          <div style={{ marginTop: 8 }}>
            <Button variant="ghost" onClick={() => onArchive(p.id)}>{t("blog.action.archive")}</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

// ─── Keywords ────────────────────────────────────────────────────────────────────

function KeywordsTab({ keywords, busy, t, onDiscover, onAdd, onStatus, onWrite }: {
  keywords: BlogKeywordT[]; busy: boolean;
  t: (k: string, v?: Record<string, string | number>) => string;
  onDiscover: () => void; onAdd: (kw: string, lang: string) => void;
  onStatus: (id: number, s: string) => void; onWrite: (id: number) => void;
}) {
  const [kw, setKw] = useState("");
  const [kl, setKl] = useState("en");
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Button onClick={onDiscover} disabled={busy}>{t("blog.action.discover")}</Button>
      </div>
      <Card>
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 160 }}>
            <Field label={t("blog.field.addKeyword")} value={kw} onChange={setKw} />
          </div>
          <select value={kl} onChange={(e) => setKl(e.target.value)} style={{ background: "var(--void)", color: "var(--arctic)", border: "1px solid var(--hairline,#23232b)", borderRadius: 8, padding: "9px 8px" }}>
            <option value="en">EN</option>
            <option value="es">ES</option>
          </select>
          <Button onClick={() => { if (kw.trim()) { onAdd(kw.trim(), kl); setKw(""); } }} disabled={busy}>{t("blog.action.add")}</Button>
        </div>
      </Card>
      {keywords.length === 0 ? (
        <p style={{ color: "var(--fg3)", fontSize: 13 }}>{t("blog.empty.keywords")}</p>
      ) : (
        keywords.map((k) => (
          <Card key={k.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <div style={{ minWidth: 0 }}>
                <span style={{ color: "var(--arctic)", fontSize: 14 }}>{k.keyword}</span>
                <span style={{ color: "var(--fg3)", fontSize: 12, marginLeft: 8 }}>
                  {k.lang} · {k.source} · {t("blog.field.score")} {k.score ?? "—"}
                </span>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <Pill tone={k.status === "planned" ? "volt" : k.status === "written" ? "success" : k.status === "vetoed" ? "warning" : "muted"}>{k.status}</Pill>
                {k.status !== "planned" && k.status !== "written" ? (
                  <Button onClick={() => onStatus(k.id, "planned")} disabled={busy}>{t("blog.action.plan")}</Button>
                ) : null}
                {k.status === "planned" ? (
                  <Button onClick={() => onWrite(k.id)} disabled={busy}>{t("blog.action.write")}</Button>
                ) : null}
                {k.status !== "vetoed" ? (
                  <Button variant="ghost" onClick={() => onStatus(k.id, "vetoed")} disabled={busy}>{t("blog.action.veto")}</Button>
                ) : null}
              </div>
            </div>
          </Card>
        ))
      )}
    </div>
  );
}

// ─── Brand DNA + autopilot ───────────────────────────────────────────────────────

function BrandTab({ config, busy, t, onSave, onAutofill }: {
  config: BlogConfigT; busy: boolean;
  t: (k: string, v?: Record<string, string | number>) => string;
  onSave: (patch: Partial<BlogConfigT>) => void;
  onAutofill: () => void;
}) {
  // Re-key on config identity so an autofill/backfill from the server repopulates the fields.
  const [voice, setVoice] = useState(config.voice || "");
  const [audience, setAudience] = useState(config.audience || "");
  const [imageStyle, setImageStyle] = useState(config.image_style || "");
  const [themes, setThemes] = useState((config.key_themes || []).join(", "));
  const [avoid, setAvoid] = useState((config.avoid_topics || []).join(", "));
  const [cadence, setCadence] = useState(String(config.cadence_per_week));
  const [autopublish, setAutopublish] = useState(config.autopublish);
  const [paused, setPaused] = useState(config.paused);
  const [en, setEn] = useState((config.languages || []).includes("en"));
  const [es, setEs] = useState((config.languages || []).includes("es"));

  const ta = { width: "100%", background: "var(--void)", color: "var(--arctic)", border: "1px solid var(--hairline,#23232b)", borderRadius: 8, padding: 10, fontSize: 13, fontFamily: "inherit" } as const;

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Card>
        <div style={{ display: "grid", gap: 10 }}>
          <label style={{ fontSize: 12, color: "var(--fg3)" }}>{t("blog.field.voice")}</label>
          <textarea value={voice} onChange={(e) => setVoice(e.target.value)} rows={2} style={ta} />
          <label style={{ fontSize: 12, color: "var(--fg3)" }}>{t("blog.field.audience")}</label>
          <textarea value={audience} onChange={(e) => setAudience(e.target.value)} rows={2} style={ta} />
          <label style={{ fontSize: 12, color: "var(--fg3)" }}>{t("blog.field.themes")}</label>
          <textarea value={themes} onChange={(e) => setThemes(e.target.value)} rows={2} style={ta} />
          <label style={{ fontSize: 12, color: "var(--fg3)" }}>{t("blog.field.avoid")}</label>
          <textarea value={avoid} onChange={(e) => setAvoid(e.target.value)} rows={2} style={ta} />
          <label style={{ fontSize: 12, color: "var(--fg3)" }}>{t("blog.field.imageStyle")}</label>
          <textarea value={imageStyle} onChange={(e) => setImageStyle(e.target.value)} rows={2} style={ta} />
        </div>
      </Card>
      <Card>
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, color: "var(--arctic)", flex: 1 }}>{t("blog.field.cadence")}</span>
            <input type="number" min={0} max={14} value={cadence} onChange={(e) => setCadence(e.target.value)}
              style={{ width: 70, background: "var(--void)", color: "var(--arctic)", border: "1px solid var(--hairline,#23232b)", borderRadius: 8, padding: "8px 10px" }} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, color: "var(--arctic)", flex: 1 }}>{t("blog.field.languages")}</span>
            <label style={{ fontSize: 13, color: "var(--fg2)", display: "flex", gap: 4, alignItems: "center" }}>
              <input type="checkbox" checked={en} onChange={(e) => setEn(e.target.checked)} /> EN
            </label>
            <label style={{ fontSize: 13, color: "var(--fg2)", display: "flex", gap: 4, alignItems: "center" }}>
              <input type="checkbox" checked={es} onChange={(e) => setEs(e.target.checked)} /> ES
            </label>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, color: "var(--arctic)", flex: 1 }}>{t("blog.field.autopublish")}</span>
            <Toggle on={autopublish} setOn={setAutopublish} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, color: "var(--arctic)", flex: 1 }}>{t("blog.field.paused")}</span>
            <Toggle on={paused} setOn={setPaused} />
          </div>
        </div>
      </Card>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Button
          disabled={busy}
          onClick={() =>
            onSave({
              voice, audience, image_style: imageStyle,
              key_themes: themes.split(",").map((s) => s.trim()).filter(Boolean),
              avoid_topics: avoid.split(",").map((s) => s.trim()).filter(Boolean),
              cadence_per_week: Math.max(0, Math.min(14, parseInt(cadence, 10) || 0)),
              autopublish, paused,
              languages: [en ? "en" : "", es ? "es" : ""].filter(Boolean),
            })
          }
        >
          {t("blog.action.save")}
        </Button>
        <Button variant="ghost" disabled={busy} onClick={onAutofill}>
          ✨ {t("blog.action.autofill")}
        </Button>
      </div>
      <p style={{ fontSize: 12, color: "var(--fg3)" }}>
        {t("blog.field.gsc")}: {config.gsc_connected ? (config.gsc_connected_email || "connected") : t("blog.field.gscNo")}
      </p>
    </div>
  );
}

// ─── Analytics (GSC) ─────────────────────────────────────────────────────────────

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ flex: 1, minWidth: 90, textAlign: "center", padding: "10px 6px", borderRadius: 10, background: "var(--obsidian)" }}>
      <div style={{ fontSize: 20, fontWeight: 800, color: "var(--arctic)" }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--fg3)" }}>{label}</div>
    </div>
  );
}

function EngineBlock({ engine, t }: {
  engine: BlogAnalyticsT["engine"];
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0);
  return (
    <Card>
      <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>{t("blog.engine.title")}</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Stat label={t("blog.engine.published")} value={engine.posts.published ?? 0} />
        <Stat label={t("blog.engine.scheduled")} value={engine.posts.scheduled ?? 0} />
        <Stat label={t("blog.engine.drafts")} value={engine.posts.draft ?? 0} />
        <Stat label={t("blog.engine.keywords")} value={sum(engine.keywords)} />
      </div>
      {engine.next_keyword && (
        <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 10 }}>
          {t("blog.engine.next")}: <span style={{ color: "var(--arctic)" }}>{engine.next_keyword}</span>
        </div>
      )}
    </Card>
  );
}

function IndexingBlock({ indexing, t }: {
  indexing: NonNullable<BlogAnalyticsT["indexing"]>;
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  return (
    <Card>
      <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>
        {t("blog.index.title", { indexed: indexing.indexed, checked: indexing.checked })}
      </div>
      <div style={{ display: "grid", gap: 6 }}>
        {indexing.urls.map((u) => (
          <div key={u.url} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13 }}>
            <span style={{ color: "var(--arctic)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {u.url.replace(/^https?:\/\/[^/]+/, "")}
            </span>
            <span style={{ color: u.verdict === "PASS" ? "var(--success,#3ddc84)" : "var(--fg3)", flexShrink: 0 }}>
              {u.error ? "?" : u.coverage || u.verdict || "—"}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function AnalyticsTab({ analytics, config, busy, t, onLoad, onConnect }: {
  analytics: BlogAnalyticsT | null; config: BlogConfigT | null; busy: boolean;
  t: (k: string, v?: Record<string, string | number>) => string;
  onLoad: () => void; onConnect: (siteUrl: string) => void;
}) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { onLoad(); }, []);
  const [siteUrl, setSiteUrl] = useState("sc-domain:blackvoltmobility.com");
  const connected = config?.gsc_connected;
  const totals = analytics?.gsc_totals;
  const days = analytics?.gsc || [];
  // Every day reporting zero is the normal state of a site that has not started ranking.
  // Saying so is the difference between "no data yet" and "this tab is broken".
  const silent = !!totals && totals.days > 0 && totals.impressions === 0;
  const latest = days.length ? days[days.length - 1] : undefined;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {analytics?.engine && <EngineBlock engine={analytics.engine} t={t} />}

      {!connected ? (
        <Card>
          <div style={{ fontSize: 13, color: "var(--fg2)", marginBottom: 12, lineHeight: 1.5 }}>{t("blog.empty.analytics")}</div>
          <Field label={t("blog.gsc.siteUrl")} value={siteUrl} onChange={setSiteUrl} />
          <div style={{ marginTop: 12 }}>
            <Button disabled={busy} onClick={() => onConnect(siteUrl)}>🔗 {t("blog.gsc.connect")}</Button>
          </div>
        </Card>
      ) : (
        <>
          <div style={{ fontSize: 12, color: "var(--fg3)" }}>
            {t("blog.field.gsc")}: {config?.gsc_connected_email || "connected"} · {config?.gsc_site_url}
          </div>
          {!totals || totals.days === 0 ? (
            <p style={{ color: "var(--fg3)", fontSize: 13 }}>{t("blog.empty.analytics")}</p>
          ) : (
            <>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Stat label={t("blog.gsc.clicks")} value={totals.clicks} />
                <Stat label={t("blog.gsc.impressions")} value={totals.impressions} />
                <Stat label="CTR" value={`${totals.ctr}%`} />
                <Stat label={t("blog.gsc.days")} value={totals.days} />
              </div>
              {silent ? (
                <Card>
                  <div style={{ fontSize: 13, color: "var(--fg2)", lineHeight: 1.55 }}>
                    {t("blog.gsc.silent", { days: totals.days })}
                  </div>
                </Card>
              ) : (
                <Card>
                  <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>{t("blog.gsc.topQueries")}</div>
                  <div style={{ display: "grid", gap: 6 }}>
                    {(latest?.top_queries || []).slice(0, 12).map((q, i) => (
                      <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13 }}>
                        <span style={{ color: "var(--arctic)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{q.query}</span>
                        <span style={{ color: "var(--fg3)", flexShrink: 0 }}>{q.clicks}c · {q.impressions}i · pos {q.position}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          )}
          {analytics?.indexing && <IndexingBlock indexing={analytics.indexing} t={t} />}
        </>
      )}
    </div>
  );
}

// ─── Speed (measured by us — see services/site_speed.py) ─────────────────────

function Mark({ v }: { v?: "ok" | "warn" }) {
  if (!v) return null;
  return (
    <span
      aria-hidden
      style={{
        display: "inline-block", width: 7, height: 7, borderRadius: 999, flexShrink: 0,
        background: v === "warn" ? "var(--danger,#ff5c5c)" : "var(--success,#3ddc84)",
      }}
    />
  );
}

function SpeedPage({ page, t }: {
  page: BlogSpeedPageT;
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  const blocking = (page.blocking_scripts ?? 0) + (page.blocking_styles ?? 0);
  const rows: Array<[string, string, string]> = [
    ["status", t("blog.speed.status"), page.error ? page.error : String(page.status ?? "—")],
    ["ttfb_ms", t("blog.speed.ttfb"), page.ttfb_ms != null ? `${page.ttfb_ms} ms` : "—"],
    ["total_ms", t("blog.speed.total"), page.total_ms != null ? `${page.total_ms} ms` : "—"],
    ["html_kb", t("blog.speed.html"), page.html_kb != null ? `${page.html_kb} KB` : "—"],
    ["compressed", t("blog.speed.compressed"), page.compressed ? "✓" : "✗"],
    ["blocking", t("blog.speed.blocking"), String(blocking)],
    [
      "images_kb",
      t("blog.speed.images"),
      page.images_kb != null ? `${page.images_kb} KB (${page.images_counted ?? 0})` : "—",
    ],
  ];
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
        <span style={{ fontWeight: 700, color: "var(--arctic)", fontSize: 14 }}>{page.path}</span>
        <span style={{ fontSize: 11, color: "var(--fg3)" }}>{page.http_version || ""}</span>
      </div>
      <div style={{ display: "grid", gap: 4 }}>
        {rows.map(([key, label, value]) => (
          <div key={key} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13 }}>
            <span style={{ color: "var(--fg3)", display: "flex", alignItems: "center", gap: 6 }}>
              <Mark v={page.verdict?.[key]} />
              {label}
            </span>
            <span style={{ color: "var(--arctic)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {value}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function SpeedTab({ analytics, busy, t, onLoad, onRun }: {
  analytics: BlogAnalyticsT | null; busy: boolean;
  t: (k: string, v?: Record<string, string | number>) => string;
  onLoad: () => void; onRun: () => void;
}) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { onLoad(); }, []);
  const speed = analytics?.speed;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <Button disabled={busy} onClick={onRun}>⚡ {t("blog.action.runSpeed")}</Button>
      <p style={{ fontSize: 12, color: "var(--fg3)", lineHeight: 1.5, margin: 0 }}>
        {t("blog.speed.method")}
      </p>
      {!speed ? (
        <p style={{ color: "var(--fg3)", fontSize: 13 }}>{t("blog.empty.speed")}</p>
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Stat label={t("blog.speed.pages")} value={speed.summary.pages} />
            <Stat label={t("blog.speed.warnings")} value={speed.summary.warnings} />
            <Stat label={t("blog.speed.slowest")} value={`${speed.summary.slowest_ttfb_ms} ms`} />
          </div>
          {speed.pages.map((p) => (
            <SpeedPage key={p.path} page={p} t={t} />
          ))}
        </>
      )}
    </div>
  );
}
