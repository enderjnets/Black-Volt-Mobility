/* Native Google Sign-In. Uses the SocialLogin plugin to obtain a Google ID token,
   then exchanges it with the backend — which, because of the `X-BV-Native` header,
   returns an opaque session token in the body — and stores that token for Bearer auth.
   All calls degrade gracefully (return { ok:false }) when off native. */
import { socialLoginPlugin } from "./nativeBridge";
import { setToken, clearToken } from "./nativeToken";

const WEB_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

let initialized = false;

async function ensureInit(): Promise<boolean> {
  const sl = socialLoginPlugin();
  if (!sl || !WEB_CLIENT_ID) return false;
  if (!initialized) {
    await sl.initialize({ google: { webClientId: WEB_CLIENT_ID } });
    initialized = true;
  }
  return true;
}

/** Best-effort init on app boot so the first tap is fast. Safe to call off native. */
export async function initSocialLogin(): Promise<void> {
  try {
    await ensureInit();
  } catch {
    /* the login() call will retry init */
  }
}

export async function nativeGoogleSignIn(
  ref?: string | null,
): Promise<{ ok: boolean; error?: string }> {
  const sl = socialLoginPlugin();
  if (!sl || !WEB_CLIENT_ID) return { ok: false, error: "native_unavailable" };
  try {
    await ensureInit();
    // No `scopes` here on purpose: requesting extra OAuth scopes forces a MainActivity
    // modification in @capgo/capacitor-social-login. The basic Google login already
    // returns an ID token carrying email / email_verified / name / sub — all the
    // backend needs — so we keep the default (no scopes).
    const res = await sl.login({ provider: "google" });
    const idToken = res?.result?.idToken;
    if (!idToken) {
      let shape = "";
      try {
        shape = JSON.stringify(res).slice(0, 240);
      } catch {
        shape = String(res);
      }
      return { ok: false, error: "no_id_token · " + shape };
    }

    // The native fetch interceptor also adds X-BV-Native; we set it explicitly too so
    // the backend returns the session token in the body regardless of interceptor timing.
    const r = await fetch("/api/v1/auth/login/google", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-BV-Native": "1" },
      body: JSON.stringify({ id_token: idToken, ref: ref || null }),
    });
    if (!r.ok) {
      const d = (await r.json().catch(() => ({}))) as { detail?: string };
      return { ok: false, error: `backend ${r.status}: ${d.detail || "login_failed"}` };
    }
    const data = (await r.json().catch(() => ({}))) as { token?: string };
    if (data.token) await setToken(data.token);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: "login_threw · " + ((e as Error)?.message || String(e)) };
  }
}

export async function nativeSignOut(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", { method: "POST" });
  } catch {
    /* clear locally regardless */
  }
  await clearToken();
  try {
    await socialLoginPlugin()?.logout({ provider: "google" });
  } catch {
    /* ignore */
  }
}
