/* Shared PWA install state.
 *
 * Chrome fires `beforeinstallprompt` once (and only when the app is installable —
 * which needs a registered service worker with a fetch handler). We capture it at
 * module load so any component (the InstallHint banner, the footer Install button)
 * can trigger the native prompt or reflect "installed". Registering the SW here on
 * every page load is what makes the app installable in the first place — previously
 * the SW was only registered when a user enabled notifications. */

type Listener = () => void;

let deferred: (Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> }) | null =
  null;
let installed = false;
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((fn) => fn());
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // stop Chrome's mini-infobar; we drive the prompt ourselves
    deferred = e as typeof deferred;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    installed = true;
    deferred = null;
    emit();
  });
}

export function installState(): { canPrompt: boolean; installed: boolean } {
  return { canPrompt: deferred != null, installed };
}

export function onInstallChange(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Fire the native install prompt. Returns the outcome, or "unavailable" when the
 * browser hasn't offered one (iOS, or the criteria aren't met yet). */
export async function triggerInstall(): Promise<"accepted" | "dismissed" | "unavailable"> {
  if (!deferred) return "unavailable";
  await deferred.prompt();
  const choice = await deferred.userChoice.catch(() => ({ outcome: "dismissed" }));
  deferred = null;
  emit();
  return choice.outcome === "accepted" ? "accepted" : "dismissed";
}

/** Register the service worker so the app qualifies as installable. Idempotent and
 * safe to call on every load. */
export function registerServiceWorker(): void {
  if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}
