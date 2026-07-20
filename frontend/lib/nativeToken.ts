/* Bearer-token store for the native app. Held in memory (read synchronously by the
   fetch interceptor) and mirrored to @capacitor/preferences so it survives restarts.
   No-op off native (no Preferences plugin present). */
import { preferencesPlugin } from "./nativeBridge";

const KEY = "bv_auth_token";
let token: string | null = null;

export function getToken(): string | null {
  return token;
}

export async function loadToken(): Promise<void> {
  const prefs = preferencesPlugin();
  if (!prefs) return;
  try {
    const { value } = await prefs.get({ key: KEY });
    token = value ?? null;
  } catch {
    /* ignore — treat as logged out */
    token = null;
  }
}

export async function setToken(t: string): Promise<void> {
  token = t;
  try {
    await preferencesPlugin()?.set({ key: KEY, value: t });
  } catch {
    /* memory copy still holds it for this session */
  }
}

export async function clearToken(): Promise<void> {
  token = null;
  try {
    await preferencesPlugin()?.remove({ key: KEY });
  } catch {
    /* ignore */
  }
}
