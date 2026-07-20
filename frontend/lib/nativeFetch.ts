/* One-time wrapper around window.fetch for the NATIVE app only: adds the bearer token
   and the `X-BV-Native` marker to same-origin `/api` requests, so the WebView uses
   token auth instead of cookies. Installed exclusively from NativeBootstrap when
   isNativeApp() is true — on the web `installNativeFetch()` is never called, so
   window.fetch is left completely untouched. */
import { getToken } from "./nativeToken";

let installed = false;

function isApiRequest(url: string): boolean {
  if (url.startsWith("/api")) return true;
  if (typeof window !== "undefined") {
    try {
      const u = new URL(url, window.location.origin);
      return u.origin === window.location.origin && u.pathname.startsWith("/api");
    } catch {
      return false;
    }
  }
  return false;
}

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return (input as Request).url;
}

export function installNativeFetch(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const orig = window.fetch.bind(window);

  const wrapped = (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    try {
      if (isApiRequest(urlOf(input))) {
        const base =
          init?.headers ??
          (input instanceof Request ? input.headers : undefined);
        const headers = new Headers(base);
        headers.set("X-BV-Native", "1");
        const tok = getToken();
        if (tok && !headers.has("Authorization")) {
          headers.set("Authorization", `Bearer ${tok}`);
        }
        return orig(input, { ...init, headers });
      }
    } catch {
      /* fall through to the unmodified fetch */
    }
    return orig(input, init);
  };

  window.fetch = wrapped as typeof window.fetch;
}
