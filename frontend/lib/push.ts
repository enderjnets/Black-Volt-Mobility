/* Web Push (PWA) client helpers — same-origin /api → backend.
 *
 * The service worker (/sw.js) receives pushes and opens the deep-link. Here we
 * register it, ask permission (only ever from a user gesture — Safari requires
 * it), create the browser PushSubscription with our VAPID public key, and mirror
 * it to the backend so it can push to this device. */
import { ApiError } from "./booking";

export interface PushConfig {
  enabled: boolean;
  public_key: string;
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new ApiError(`${path}:${r.status}`, r.status);
  return r.json();
}

async function jpost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new ApiError(`${path}:${r.status}`, r.status);
  return r.json();
}

export function getPushConfig(): Promise<PushConfig> {
  return jget<PushConfig>("/v1/push/config");
}

/** True when the platform can do Web Push at all (Notification + SW + PushManager). */
export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** Running as an installed PWA (standalone display). iOS needs this for push. */
export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    // iOS Safari exposes navigator.standalone on home-screen web apps.
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

export function isIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  return (
    /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    // iPadOS 13+ reports as Mac; detect the touch-capable variant.
    (navigator.platform === "MacIntel" && (navigator as unknown as { maxTouchPoints?: number }).maxTouchPoints! > 1)
  );
}

export function notificationPermission(): NotificationPermission | "unsupported" {
  if (!pushSupported()) return "unsupported";
  return Notification.permission;
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function registerSW(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register("/sw.js");
}

/** Whether this device already has an active push subscription mirrored to us. */
export async function isSubscribed(): Promise<boolean> {
  if (!pushSupported() || Notification.permission !== "granted") return false;
  try {
    const reg = await navigator.serviceWorker.getRegistration("/sw.js");
    if (!reg) return false;
    return (await reg.pushManager.getSubscription()) != null;
  } catch {
    return false;
  }
}

/** Register the SW, request permission (must be called from a user gesture),
 * subscribe, and mirror to the backend. Returns true on success. */
export async function subscribePush(): Promise<boolean> {
  if (!pushSupported()) return false;
  const cfg = await getPushConfig();
  if (!cfg.enabled || !cfg.public_key) return false;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return false;

  const reg = await registerSW();
  await navigator.serviceWorker.ready;

  const existing = await reg.pushManager.getSubscription();
  const sub =
    existing ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(cfg.public_key),
    }));

  const json = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) return false;

  await jpost("/v1/push/subscribe", {
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
  });
  return true;
}

/** Unsubscribe this device and tell the backend to forget it. */
export async function unsubscribePush(): Promise<void> {
  if (!pushSupported()) return;
  const reg = await navigator.serviceWorker.getRegistration("/sw.js");
  const sub = reg && (await reg.pushManager.getSubscription());
  if (!sub) return;
  const endpoint = sub.endpoint;
  try {
    await sub.unsubscribe();
  } finally {
    await jpost("/v1/push/unsubscribe", { endpoint }).catch(() => {});
  }
}
