/* Type-safe accessors to the Capacitor native plugins, reached through the
   runtime-injected `window.Capacitor.Plugins` global — deliberately NO `@capacitor/*`
   import so the Next.js web build / SSR stays clean (every accessor returns null off
   native). The plugins themselves are installed in `mobile/` and linked via `cap sync`. */

export interface PluginListenerHandle {
  remove: () => Promise<void>;
}

export interface SocialLoginPlugin {
  initialize(options: {
    google?: { webClientId?: string; mode?: "online" | "offline" };
  }): Promise<void>;
  login(options: {
    provider: "google";
    options?: { scopes?: string[] };
  }): Promise<{ provider: string; result?: { idToken?: string | null } | null }>;
  logout(options: { provider: "google" }): Promise<void>;
}

export type PushPermissionState =
  | "prompt"
  | "prompt-with-rationale"
  | "granted"
  | "denied";

export interface PushNotificationsPlugin {
  checkPermissions(): Promise<{ receive: PushPermissionState }>;
  requestPermissions(): Promise<{ receive: PushPermissionState }>;
  register(): Promise<void>;
  addListener(
    event: string,
    cb: (data: unknown) => void,
  ): Promise<PluginListenerHandle>;
}

export interface PreferencesPlugin {
  get(options: { key: string }): Promise<{ value: string | null }>;
  set(options: { key: string; value: string }): Promise<void>;
  remove(options: { key: string }): Promise<void>;
}

interface CapacitorPlugins {
  SocialLogin?: SocialLoginPlugin;
  PushNotifications?: PushNotificationsPlugin;
  Preferences?: PreferencesPlugin;
}

function plugins(): CapacitorPlugins | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as unknown as { Capacitor?: { Plugins?: CapacitorPlugins } })
    .Capacitor?.Plugins;
}

export function socialLoginPlugin(): SocialLoginPlugin | null {
  return plugins()?.SocialLogin ?? null;
}

export function pushPlugin(): PushNotificationsPlugin | null {
  return plugins()?.PushNotifications ?? null;
}

export function preferencesPlugin(): PreferencesPlugin | null {
  return plugins()?.Preferences ?? null;
}
