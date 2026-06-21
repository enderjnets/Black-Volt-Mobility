"use client";

import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";

import { Icon } from "../Icon";
import { Button, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";
import {
  type SocialAccount,
  type SocialAnalytics,
  type SocialInteraction,
  type SocialPlatform,
  type SocialPost,
  type UploadedRef,
  approvePost,
  deletePost,
  dismissInteraction,
  draftReply,
  generateFromImage,
  generatePost,
  getAnalytics,
  listAccounts,
  listInbox,
  listPosts,
  publishPost,
  rejectPost,
  renderPost,
  sendReply,
  syncBufferChannels,
  updatePost,
  uploadReferenceImage,
} from "@/lib/social";

const MAX_REFS = 4;
const ACCEPT_IMG = "image/png,image/jpeg,image/webp,image/gif";

type Tab = "create" | "queue" | "inbox" | "accounts";

const PLATFORM_ICON: Record<string, string> = {
  instagram: "instagram",
  facebook: "facebook",
  tiktok: "music",
};

function Panel({ title, icon, children }: { title?: string; icon?: string; children: ReactNode }) {
  return (
    <div
      style={{
        background: "var(--obsidian)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-lg)",
        padding: 18,
      }}
    >
      {title && (
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 14 }}>
          {icon && <Icon name={icon} size={18} color="var(--volt)" />}
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 700,
              fontSize: 16,
              color: "var(--arctic)",
              margin: 0,
            }}
          >
            {title}
          </h2>
        </div>
      )}
      {children}
    </div>
  );
}

function Kpi({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div
      style={{
        background: "var(--obsidian)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-lg)",
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 6,
        minWidth: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <Icon name={icon} size={15} color="var(--volt)" />
        <span style={{ fontSize: 12, color: "var(--fg3)", fontFamily: "var(--font-sans)" }}>{label}</span>
      </div>
      <span
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          fontSize: 26,
          color: "var(--arctic)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </span>
    </div>
  );
}

const STATUS_TONE: Record<string, "volt" | "success" | "warning" | "muted"> = {
  draft: "muted",
  render_requested: "warning",
  rendered: "volt",
  approved: "volt",
  scheduled: "warning",
  published: "success",
  failed: "warning",
};

function mediaUrl(path: string | null): string | null {
  // Real assets are stored as a rel path under the public /media mount.
  if (!path || path.startsWith("simulated://")) return null;
  return path.startsWith("/") ? path : `/media/${path}`;
}

function MediaPreview({ post }: { post: SocialPost }) {
  const { t } = useI18n();
  const src = post.simulated_render ? null : mediaUrl(post.media_path);
  const poster = mediaUrl(post.cover_path) ?? undefined;
  const box: CSSProperties = {
    width: 90,
    flexShrink: 0,
    aspectRatio: "9 / 16",
    borderRadius: "var(--radius-md)",
    background: "var(--obsidian-3)",
    border: "1px solid var(--line-strong)",
    overflow: "hidden",
  };
  if (src) {
    return (
      <video
        src={src}
        poster={poster}
        controls
        muted
        playsInline
        preload="metadata"
        style={{ ...box, objectFit: "cover", display: "block" }}
      />
    );
  }
  return (
    <div
      style={{
        ...box,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        textAlign: "center",
        padding: 6,
      }}
    >
      <Icon name="video" size={22} color="var(--volt)" />
      {post.simulated_render && (
        <span style={{ fontSize: 9, color: "var(--fg3)", lineHeight: 1.2 }}>
          {t("dash.social.simulatedRender")}
        </span>
      )}
    </div>
  );
}

const RENDER_STAGES = [
  "queued",
  "voiceover",
  "images",
  "scenes",
  "backgrounds",
  "assembling",
  "encoding",
];

function RenderProgress({ post }: { post: SocialPost }) {
  const { t } = useI18n();
  const pct =
    typeof post.render_progress === "number"
      ? Math.max(0, Math.min(100, Math.round(post.render_progress)))
      : null;
  const stageKey = post.render_stage || "queued";
  const stageLabel = RENDER_STAGES.includes(stageKey)
    ? t(`dash.social.render.stage.${stageKey}`)
    : stageKey;
  return (
    <div style={{ marginTop: 12 }} aria-live="polite">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
          marginBottom: 6,
        }}
      >
        <span
          style={{
            fontSize: 12,
            color: "var(--fg2)",
            display: "flex",
            alignItems: "center",
            gap: 6,
            minWidth: 0,
          }}
        >
          <Icon name="clock" size={13} color="var(--volt)" />
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {t("dash.social.render.rendering")} · {stageLabel}
          </span>
        </span>
        {pct !== null && (
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--volt)", flexShrink: 0 }}>
            {pct}%
          </span>
        )}
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 999,
          background: "var(--obsidian-3)",
          overflow: "hidden",
          position: "relative",
        }}
      >
        {pct !== null ? (
          <div
            style={{
              height: "100%",
              width: `${pct}%`,
              background: "var(--volt)",
              borderRadius: 999,
              transition: "width .4s ease",
            }}
          />
        ) : (
          <div
            style={{
              position: "absolute",
              top: 0,
              height: "100%",
              width: "40%",
              background: "var(--volt)",
              borderRadius: 999,
              animation: "bvRenderIndet 1.2s ease-in-out infinite",
            }}
          />
        )}
      </div>
    </div>
  );
}

export function SocialMedia() {
  const { t, lang } = useI18n();
  const [tab, setTab] = useState<Tab>("create");
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [inbox, setInbox] = useState<SocialInteraction[]>([]);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [stats, setStats] = useState<SocialAnalytics | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [topic, setTopic] = useState("");
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const [replyEdits, setReplyEdits] = useState<Record<number, string>>({});
  const [refs, setRefs] = useState<UploadedRef[]>([]);
  const refInput = useRef<HTMLInputElement>(null);
  const fromImgInput = useRef<HTMLInputElement>(null);

  const setBusyKey = (k: string, on: boolean) =>
    setBusy((s) => {
      const n = new Set(s);
      if (on) n.add(k);
      else n.delete(k);
      return n;
    });
  const isBusy = (k: string) => busy.has(k);

  async function refresh() {
    try {
      const [p, ix, ac, an] = await Promise.all([
        listPosts(),
        listInbox(),
        listAccounts(),
        getAnalytics(),
      ]);
      setPosts(p);
      setInbox(ix);
      setAccounts(ac);
      setStats(an);
      setErr(null);
    } catch {
      setErr(t("dash.social.error"));
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // While any post is actively rendering, poll its status (and live progress)
  // every 3s so the progress bar advances and the video appears on completion.
  // Capped at ~25 min so a dead worker never leaves us polling forever.
  const hasRendering = posts.some((p) => p.status === "render_requested");
  useEffect(() => {
    if (!hasRendering) return;
    let elapsed = 0;
    const id = setInterval(async () => {
      elapsed += 3000;
      if (elapsed > 25 * 60 * 1000) {
        clearInterval(id);
        return;
      }
      try {
        setPosts(await listPosts());
      } catch {
        /* transient; keep last good state, mount/action refresh surfaces errors */
      }
    }, 3000);
    return () => clearInterval(id);
  }, [hasRendering]);

  async function onGenerate() {
    if (isBusy("gen")) return;
    setBusyKey("gen", true);
    try {
      await generatePost({
        topic: topic.trim() || undefined,
        lang,
        reference_paths: refs.length ? refs.map((r) => r.path) : undefined,
      });
      setTopic("");
      setRefs([]);
      await refresh();
      setTab("queue");
    } catch {
      setErr(t("dash.social.error"));
    } finally {
      setBusyKey("gen", false);
    }
  }

  async function onPickRefs(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    setBusyKey("refs", true);
    try {
      const room = MAX_REFS - refs.length;
      const uploaded: UploadedRef[] = [];
      for (const f of files.slice(0, Math.max(0, room))) {
        uploaded.push(await uploadReferenceImage(f));
      }
      if (uploaded.length) setRefs((s) => [...s, ...uploaded].slice(0, MAX_REFS));
    } catch {
      setErr(t("dash.social.error"));
    } finally {
      setBusyKey("refs", false);
    }
  }

  async function onGenerateFromImage(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || isBusy("fromImg")) return;
    setBusyKey("fromImg", true);
    try {
      await generateFromImage(file, { lang });
      await refresh();
      setTab("queue");
    } catch {
      setErr(t("dash.social.fromImage.error"));
    } finally {
      setBusyKey("fromImg", false);
    }
  }

  async function postAction(key: string, fn: () => Promise<unknown>) {
    if (isBusy(key)) return;
    setBusyKey(key, true);
    try {
      await fn();
      await refresh();
    } catch {
      setErr(t("dash.social.error"));
    } finally {
      setBusyKey(key, false);
    }
  }

  const onSyncBuffer = async () => {
    setSyncing(true);
    try {
      const next = await syncBufferChannels();
      setAccounts(next);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(false);
    }
  };

  const tabs: { id: Tab; label: string; icon: string; badge?: number }[] = [
    { id: "create", label: t("dash.social.tab.create"), icon: "sparkles" },
    { id: "queue", label: t("dash.social.tab.queue"), icon: "video", badge: posts.length || undefined },
    {
      id: "inbox",
      label: t("dash.social.tab.inbox"),
      icon: "message-circle",
      badge: stats?.pending_replies || undefined,
    },
    { id: "accounts", label: t("dash.social.tab.accounts"), icon: "share-2" },
  ];

  // Posts awaiting the owner's decision (auto-generated daily + manual drafts alike).
  const pendingDaily = posts.filter((p) =>
    ["draft", "render_requested", "rendered", "approved", "scheduled"].includes(p.status),
  );

  return (
    <div style={{ padding: "20px 16px 120px", maxWidth: 920, margin: "0 auto" }}>
      <p style={{ color: "var(--fg2)", fontSize: 14, margin: "0 0 16px", fontFamily: "var(--font-sans)" }}>
        {t("dash.social.subtitle")}
      </p>

      {/* KPIs */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: 10,
          marginBottom: 16,
        }}
      >
        <Kpi icon="video" label={t("dash.social.kpi.posts")} value={String(stats?.posts_total ?? 0)} />
        <Kpi icon="send" label={t("dash.social.kpi.published")} value={String(stats?.posts_published ?? 0)} />
        <Kpi icon="eye" label={t("dash.social.kpi.views")} value={String(stats?.views ?? 0)} />
        <Kpi
          icon="message-circle"
          label={t("dash.social.kpi.replies")}
          value={String(stats?.pending_replies ?? 0)}
        />
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {tabs.map((tb) => {
          const active = tab === tb.id;
          return (
            <button
              key={tb.id}
              onClick={() => setTab(tb.id)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                minHeight: 40,
                padding: "8px 14px",
                borderRadius: "var(--radius-full)",
                border: `1px solid ${active ? "var(--volt-border)" : "var(--line-strong)"}`,
                background: active ? "var(--volt-bg)" : "transparent",
                color: active ? "var(--volt)" : "var(--silver)",
                cursor: "pointer",
                fontFamily: "var(--font-sans)",
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              <Icon name={tb.icon} size={15} color="currentColor" />
              {tb.label}
              {tb.badge ? (
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    background: active ? "var(--volt)" : "var(--obsidian-3)",
                    color: active ? "var(--void)" : "var(--silver)",
                    borderRadius: 99,
                    padding: "0 6px",
                    minWidth: 16,
                    textAlign: "center",
                  }}
                >
                  {tb.badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {err && (
        <div
          style={{
            background: "rgba(255,92,110,0.1)",
            border: "1px solid rgba(255,92,110,0.4)",
            color: "var(--danger)",
            borderRadius: "var(--radius-md)",
            padding: "10px 14px",
            fontSize: 13,
            marginBottom: 14,
          }}
        >
          {err}
        </div>
      )}

      {tab === "create" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Panel title={t("dash.social.generate.title")} icon="sparkles">
            <label style={{ display: "block" }}>
              <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7 }}>
                {t("dash.social.generate.topic")}
              </div>
              <textarea
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder={t("dash.social.generate.placeholder")}
                rows={2}
                maxLength={200}
                style={{
                  width: "100%",
                  background: "var(--obsidian-3)",
                  border: "1px solid var(--line-strong)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--arctic)",
                  fontSize: 14,
                  fontFamily: "var(--font-sans)",
                  padding: "12px 14px",
                  resize: "vertical",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              />
            </label>

            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7 }}>
                {t("dash.social.refs.label")}
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {refs.map((r, i) => (
                  <div
                    key={r.path}
                    style={{
                      position: "relative",
                      width: 64,
                      height: 64,
                      borderRadius: "var(--radius-md)",
                      overflow: "hidden",
                      border: "1px solid var(--line)",
                      background: "var(--void)",
                    }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={r.public_url ?? `/media/${r.path}`}
                      alt={`reference ${i + 1}`}
                      style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                    />
                    <button
                      onClick={() => setRefs((s) => s.filter((_, j) => j !== i))}
                      title={t("dash.social.refs.remove")}
                      style={{
                        position: "absolute",
                        top: 3,
                        right: 3,
                        width: 20,
                        height: 20,
                        borderRadius: "50%",
                        border: "none",
                        cursor: "pointer",
                        background: "rgba(10,10,15,0.8)",
                        color: "var(--arctic)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <Icon name="x" size={12} color="currentColor" />
                    </button>
                  </div>
                ))}
                {refs.length < MAX_REFS && (
                  <button
                    onClick={() => refInput.current?.click()}
                    disabled={isBusy("refs")}
                    style={{
                      width: 64,
                      height: 64,
                      borderRadius: "var(--radius-md)",
                      border: "1.5px dashed var(--line-strong)",
                      background: "var(--obsidian-3)",
                      color: "var(--silver)",
                      cursor: isBusy("refs") ? "default" : "pointer",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 3,
                      fontSize: 10,
                      textAlign: "center",
                      padding: 4,
                    }}
                  >
                    <Icon name="plus" size={16} color="var(--volt)" />
                    {isBusy("refs") ? t("dash.social.refs.adding") : t("dash.social.refs.add")}
                  </button>
                )}
              </div>
              <p style={{ fontSize: 11.5, color: "var(--fg3)", margin: "8px 0 0", lineHeight: 1.5 }}>
                {t("dash.social.refs.hint")}
              </p>
              <input
                ref={refInput}
                type="file"
                accept={ACCEPT_IMG}
                multiple
                onChange={onPickRefs}
                style={{ display: "none" }}
              />
            </div>

            <div style={{ marginTop: 12 }}>
              <Button variant="solid" icon="sparkles" onClick={onGenerate} disabled={isBusy("gen")} full>
                {isBusy("gen") ? t("dash.social.generate.generating") : t("dash.social.generate.btn")}
              </Button>
            </div>
            <p style={{ fontSize: 12, color: "var(--fg3)", marginTop: 12, lineHeight: 1.5 }}>
              {t("dash.social.generate.hint")}
            </p>
          </Panel>

          <Panel title={t("dash.social.fromImage.title")} icon="image">
            <p style={{ fontSize: 12, color: "var(--fg3)", margin: "0 0 12px", lineHeight: 1.5 }}>
              {t("dash.social.fromImage.hint")}
            </p>
            <Button
              variant="solid"
              icon="upload"
              onClick={() => fromImgInput.current?.click()}
              disabled={isBusy("fromImg")}
              full
            >
              {isBusy("fromImg")
                ? t("dash.social.fromImage.generating")
                : t("dash.social.fromImage.btn")}
            </Button>
            <input
              ref={fromImgInput}
              type="file"
              accept={ACCEPT_IMG}
              onChange={onGenerateFromImage}
              style={{ display: "none" }}
            />
          </Panel>

          <Panel title={t("dash.social.daily.title")} icon="sparkles">
            <p style={{ fontSize: 12, color: "var(--fg3)", margin: "0 0 12px", lineHeight: 1.5 }}>
              {t("dash.social.daily.hint")}
            </p>
            {pendingDaily.length === 0 ? (
              <p style={{ color: "var(--fg3)", fontSize: 14, margin: 0 }}>
                {t("dash.social.daily.empty")}
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {pendingDaily.map((p) => (
                  <PostCard
                    key={p.id}
                    post={p}
                    isBusy={isBusy}
                    onRender={() => postAction(`render-${p.id}`, () => renderPost(p.id))}
                    onApprove={() => postAction(`approve-${p.id}`, () => approvePost(p.id))}
                    onReject={(reason) => postAction(`reject-${p.id}`, () => rejectPost(p.id, reason))}
                    onUpdateRefs={(paths) => postAction(`refs-${p.id}`, () => updatePost(p.id, { reference_image_paths: paths }))}
                    onPublish={() => postAction(`publish-${p.id}`, () => publishPost(p.id))}
                    onDelete={() => postAction(`delete-${p.id}`, () => deletePost(p.id))}
                  />
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {tab === "queue" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {posts.length === 0 ? (
            <Panel>
              <p style={{ color: "var(--fg3)", fontSize: 14, margin: 0 }}>{t("dash.social.queue.empty")}</p>
            </Panel>
          ) : (
            posts.map((p) => (
              <PostCard
                key={p.id}
                post={p}
                isBusy={isBusy}
                onRender={() => postAction(`render-${p.id}`, () => renderPost(p.id))}
                onApprove={() => postAction(`approve-${p.id}`, () => approvePost(p.id))}
                onReject={(reason) => postAction(`reject-${p.id}`, () => rejectPost(p.id, reason))}
                onUpdateRefs={(paths) => postAction(`refs-${p.id}`, () => updatePost(p.id, { reference_image_paths: paths }))}
                onPublish={() => postAction(`publish-${p.id}`, () => publishPost(p.id))}
                onDelete={() => postAction(`delete-${p.id}`, () => deletePost(p.id))}
              />
            ))
          )}
        </div>
      )}

      {tab === "inbox" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {inbox.length === 0 ? (
            <Panel>
              <p style={{ color: "var(--fg3)", fontSize: 14, margin: 0 }}>{t("dash.social.inbox.empty")}</p>
            </Panel>
          ) : (
            inbox.map((it) => (
              <InboxCard
                key={it.id}
                it={it}
                draftValue={replyEdits[it.id]}
                onDraftChange={(v) => setReplyEdits((s) => ({ ...s, [it.id]: v }))}
                isBusy={isBusy}
                onDraft={() => postAction(`draft-${it.id}`, () => draftReply(it.id))}
                onSend={() =>
                  postAction(`send-${it.id}`, () =>
                    sendReply(it.id, replyEdits[it.id] ?? it.ai_draft ?? undefined),
                  )
                }
                onDismiss={() => postAction(`dismiss-${it.id}`, () => dismissInteraction(it.id))}
              />
            ))
          )}
        </div>
      )}

      {tab === "accounts" && (
        <Panel title={t("dash.social.accounts.title")} icon="share-2">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
            <Button variant="solid" size="sm" icon="refresh-cw" onClick={onSyncBuffer} disabled={syncing}>
              {syncing ? t("dash.social.accounts.syncing") : t("dash.social.accounts.sync")}
            </Button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {accounts.map((a) => (
              <div
                key={a.platform}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 14px",
                  borderRadius: "var(--radius-md)",
                  background: "var(--obsidian-2)",
                  border: "1px solid var(--line)",
                  flexWrap: "wrap",
                }}
              >
                <Icon name={PLATFORM_ICON[a.platform] || "share-2"} size={22} color="var(--arctic)" />
                <div style={{ flex: 1, minWidth: 120 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", textTransform: "capitalize" }}>
                    {a.display_name || a.platform}
                  </div>
                  <div style={{ fontSize: 12, color: a.connected ? "var(--cyan)" : "var(--fg3)" }}>
                    {a.connected ? t("dash.social.accounts.connected") : t("dash.social.accounts.disconnected")}
                  </div>
                </div>
                {!a.connected && (
                  <a
                    href="https://publish.buffer.com"
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: 12, color: "var(--cyan)", textDecoration: "none" }}
                  >
                    {t("dash.social.accounts.connectInBuffer")}
                  </a>
                )}
              </div>
            ))}
          </div>
          <p style={{ fontSize: 12, color: "var(--fg3)", marginTop: 14, lineHeight: 1.5 }}>
            {t("dash.social.accounts.viaBuffer")}
          </p>
        </Panel>
      )}
    </div>
  );
}

function chipStyle(): CSSProperties {
  return {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--silver)",
    background: "var(--obsidian-3)",
    border: "1px solid var(--line-strong)",
    borderRadius: "var(--radius-full)",
    padding: "3px 9px",
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    textTransform: "capitalize",
  };
}

function PostCard({
  post,
  isBusy,
  onRender,
  onApprove,
  onReject,
  onUpdateRefs,
  onPublish,
  onDelete,
}: {
  post: SocialPost;
  isBusy: (k: string) => boolean;
  onRender: () => void;
  onApprove: () => void;
  onReject: (reason?: string) => void;
  onUpdateRefs: (paths: string[]) => void;
  onPublish: () => void;
  onDelete: () => void;
}) {
  const { t } = useI18n();
  const s = post.status;
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [editImgs, setEditImgs] = useState(false);
  const [imgList, setImgList] = useState<string[]>(post.reference_image_paths);
  const [imgBusy, setImgBusy] = useState(false);
  const imgInput = useRef<HTMLInputElement>(null);
  const anyBusy = ["render", "approve", "reject", "publish", "delete", "refs"].some((a) => isBusy(`${a}-${post.id}`));
  const rejectBusy = isBusy(`reject-${post.id}`);
  const refsBusy = isBusy(`refs-${post.id}`);
  const editable = s === "draft" || s === "failed" || s === "rendered";

  async function onAddImg(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    setImgBusy(true);
    try {
      const room = MAX_REFS - imgList.length;
      const added: string[] = [];
      for (const f of files.slice(0, Math.max(0, room))) {
        added.push((await uploadReferenceImage(f)).path);
      }
      if (added.length) setImgList((s2) => [...s2, ...added].slice(0, MAX_REFS));
    } catch {
      /* surfaced by the parent's error banner on save; keep the picker resilient */
    } finally {
      setImgBusy(false);
    }
  }
  return (
    <Panel>
      <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
        <MediaPreview post={post} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <Pill tone={STATUS_TONE[s] || "muted"}>{t(`dash.social.status.${s}`)}</Pill>
            {post.source && (
              <span style={chipStyle()}>
                <Icon name="sparkles" size={11} color="currentColor" />
                {post.source === "ai" ? t("dash.social.byAI") : t("dash.social.byTemplate")}
              </span>
            )}
          </div>
          {post.caption && (
            <p
              style={{
                fontSize: 13.5,
                color: "var(--arctic)",
                margin: "0 0 8px",
                lineHeight: 1.5,
                fontFamily: "var(--font-sans)",
                whiteSpace: "pre-wrap",
              }}
            >
              {post.caption}
            </p>
          )}
          {post.hashtags && (
            <p style={{ fontSize: 12.5, color: "var(--volt)", margin: "0 0 10px", lineHeight: 1.5 }}>
              {post.hashtags}
            </p>
          )}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
            {post.targets.map((tg) => (
              <span key={tg} style={chipStyle()}>
                <Icon name={PLATFORM_ICON[tg] || "share-2"} size={11} color="currentColor" />
                {tg}
              </span>
            ))}
          </div>
          {post.scheduled_at && s === "scheduled" && (
            <p style={{ fontSize: 12, color: "var(--warning)", margin: "4px 0 0" }}>
              {t("dash.social.scheduledFor", { when: new Date(post.scheduled_at).toLocaleString() })}
            </p>
          )}
          {post.rejection_reason && s === "draft" && (
            <p style={{ fontSize: 12, color: "var(--fg3)", margin: "4px 0 0", lineHeight: 1.4 }}>
              {t("dash.social.reject.note", { reason: post.rejection_reason })}
            </p>
          )}
        </div>
      </div>

      {s === "render_requested" && <RenderProgress post={post} />}

      {rejecting && (
        <div style={{ marginTop: 12 }}>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t("dash.social.reject.why")}
            rows={2}
            autoFocus
            style={{
              width: "100%",
              background: "var(--obsidian-3)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-md)",
              color: "var(--arctic)",
              fontSize: 13.5,
              fontFamily: "var(--font-sans)",
              padding: "10px 12px",
              resize: "vertical",
              outline: "none",
              boxSizing: "border-box",
              marginBottom: 10,
            }}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button
              variant="solid"
              size="sm"
              icon="sparkles"
              onClick={() => {
                onReject(reason.trim() || undefined);
                setRejecting(false);
                setReason("");
              }}
              disabled={rejectBusy}
            >
              {rejectBusy ? t("dash.social.action.working") : t("dash.social.reject.submit")}
            </Button>
            <Button
              variant="plain"
              size="sm"
              icon="x"
              onClick={() => {
                setRejecting(false);
                setReason("");
              }}
              disabled={rejectBusy}
            >
              {t("dash.social.reject.cancel")}
            </Button>
          </div>
        </div>
      )}

      {editImgs && (
        <div style={{ marginTop: 12 }}>
          <p style={{ fontSize: 12, color: "var(--fg3)", margin: "0 0 8px", lineHeight: 1.4 }}>
            {t("dash.social.images.hint")}
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            {imgList.length === 0 && (
              <span style={{ fontSize: 12, color: "var(--fg3)" }}>{t("dash.social.images.none")}</span>
            )}
            {imgList.map((p, i) => (
              <div
                key={p}
                style={{
                  position: "relative",
                  width: 64,
                  height: 64,
                  borderRadius: "var(--radius-md)",
                  overflow: "hidden",
                  border: "1px solid var(--line)",
                  background: "var(--void)",
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={mediaUrl(p) ?? `/media/${p}`}
                  alt={`image ${i + 1}`}
                  style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                />
                <button
                  onClick={() => setImgList((s2) => s2.filter((_, j) => j !== i))}
                  title={t("dash.social.refs.remove")}
                  disabled={refsBusy}
                  style={{
                    position: "absolute",
                    top: 3,
                    right: 3,
                    width: 20,
                    height: 20,
                    borderRadius: "50%",
                    border: "none",
                    cursor: refsBusy ? "default" : "pointer",
                    background: "rgba(10,10,15,0.8)",
                    color: "var(--arctic)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Icon name="x" size={12} color="currentColor" />
                </button>
              </div>
            ))}
            {imgList.length < MAX_REFS && (
              <button
                onClick={() => imgInput.current?.click()}
                disabled={imgBusy || refsBusy}
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: "var(--radius-md)",
                  border: "1.5px dashed var(--line-strong)",
                  background: "var(--obsidian-3)",
                  color: "var(--silver)",
                  cursor: imgBusy ? "default" : "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 3,
                  fontSize: 10,
                  textAlign: "center",
                  padding: 4,
                }}
              >
                <Icon name="plus" size={16} color="var(--volt)" />
                {imgBusy ? t("dash.social.refs.adding") : t("dash.social.refs.add")}
              </button>
            )}
          </div>
          <input
            ref={imgInput}
            type="file"
            accept={ACCEPT_IMG}
            multiple
            onChange={onAddImg}
            style={{ display: "none" }}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button
              variant="solid"
              size="sm"
              icon="check"
              onClick={() => {
                onUpdateRefs(imgList);
                setEditImgs(false);
              }}
              disabled={refsBusy || imgBusy}
            >
              {refsBusy ? t("dash.social.action.working") : t("dash.social.images.save")}
            </Button>
            <Button
              variant="plain"
              size="sm"
              icon="x"
              onClick={() => {
                setImgList(post.reference_image_paths);
                setEditImgs(false);
              }}
              disabled={refsBusy}
            >
              {t("dash.social.action.cancel")}
            </Button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
        {(s === "draft" || s === "failed") && (
          <Button variant="solid" size="sm" icon="video" onClick={onRender} disabled={anyBusy}>
            {isBusy(`render-${post.id}`) ? t("dash.social.action.working") : t("dash.social.action.render")}
          </Button>
        )}
        {editable && !editImgs && !rejecting && (
          <Button
            variant="ghost"
            size="sm"
            icon="image"
            onClick={() => {
              setImgList(post.reference_image_paths);
              setEditImgs(true);
            }}
            disabled={anyBusy}
          >
            {t("dash.social.images.edit")}
          </Button>
        )}
        {s === "rendered" && (
          <Button variant="solid" size="sm" icon="check" onClick={onApprove} disabled={anyBusy}>
            {isBusy(`approve-${post.id}`) ? t("dash.social.action.working") : t("dash.social.action.approve")}
          </Button>
        )}
        {(s === "approved" || s === "scheduled") && (
          <Button variant="solid" size="sm" icon="send" onClick={onPublish} disabled={anyBusy}>
            {isBusy(`publish-${post.id}`) ? t("dash.social.action.working") : t("dash.social.action.publish")}
          </Button>
        )}
        {(s === "rendered" || s === "approved" || s === "scheduled") && !rejecting && (
          <Button
            variant="ghost"
            size="sm"
            icon="x"
            onClick={() => setRejecting(true)}
            disabled={anyBusy}
          >
            {t("dash.social.action.reject")}
          </Button>
        )}
        <Button variant="plain" size="sm" icon="trash-2" onClick={onDelete} disabled={anyBusy}>
          {t("dash.social.action.delete")}
        </Button>
      </div>
    </Panel>
  );
}

function InboxCard({
  it,
  draftValue,
  onDraftChange,
  isBusy,
  onDraft,
  onSend,
  onDismiss,
}: {
  it: SocialInteraction;
  draftValue: string | undefined;
  onDraftChange: (v: string) => void;
  isBusy: (k: string) => boolean;
  onDraft: () => void;
  onSend: () => void;
  onDismiss: () => void;
}) {
  const { t } = useI18n();
  const value = draftValue ?? it.ai_draft ?? "";
  const sent = it.reply_status === "sent";
  const dismissed = it.reply_status === "dismissed";
  return (
    <Panel>
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 8, flexWrap: "wrap" }}>
        <Icon name={PLATFORM_ICON[it.platform] || "share-2"} size={18} color="var(--arctic)" />
        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)" }}>
          {it.author_handle || "—"}
        </span>
        {sent && <Pill tone="success">{t("dash.social.inbox.sent")}</Pill>}
        {dismissed && <Pill tone="muted">{t("dash.social.inbox.dismissed")}</Pill>}
      </div>
      <p
        style={{
          fontSize: 13.5,
          color: "var(--fg2)",
          margin: "0 0 12px",
          lineHeight: 1.5,
          fontFamily: "var(--font-sans)",
          whiteSpace: "pre-wrap",
        }}
      >
        {it.text}
      </p>

      {!sent && !dismissed && (
        <>
          {it.ai_draft ? (
            <>
              <textarea
                value={value}
                onChange={(e) => onDraftChange(e.target.value)}
                placeholder={t("dash.social.inbox.replyPlaceholder")}
                rows={3}
                style={{
                  width: "100%",
                  background: "var(--obsidian-3)",
                  border: "1px solid var(--line-strong)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--arctic)",
                  fontSize: 13.5,
                  fontFamily: "var(--font-sans)",
                  padding: "10px 12px",
                  resize: "vertical",
                  outline: "none",
                  boxSizing: "border-box",
                  marginBottom: 10,
                }}
              />
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Button
                  variant="solid"
                  size="sm"
                  icon="send"
                  onClick={onSend}
                  disabled={isBusy(`send-${it.id}`)}
                >
                  {isBusy(`send-${it.id}`) ? t("dash.social.action.working") : t("dash.social.inbox.send")}
                </Button>
                <Button variant="plain" size="sm" icon="x" onClick={onDismiss}>
                  {t("dash.social.inbox.dismiss")}
                </Button>
              </div>
            </>
          ) : (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Button
                variant="solid"
                size="sm"
                icon="sparkles"
                onClick={onDraft}
                disabled={isBusy(`draft-${it.id}`)}
              >
                {isBusy(`draft-${it.id}`)
                  ? t("dash.social.inbox.drafting")
                  : t("dash.social.inbox.draft")}
              </Button>
              <Button variant="plain" size="sm" icon="x" onClick={onDismiss}>
                {t("dash.social.inbox.dismiss")}
              </Button>
            </div>
          )}
        </>
      )}

      {sent && it.ai_draft && (
        <p
          style={{
            fontSize: 13,
            color: "var(--silver)",
            background: "var(--obsidian-2)",
            borderLeft: "2px solid var(--success)",
            borderRadius: 4,
            padding: "8px 12px",
            margin: 0,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
          }}
        >
          {it.ai_draft}
        </p>
      )}
    </Panel>
  );
}
