/* Detect whether the web app is running inside the Black Volt native shell
   (Capacitor). Reads the runtime global the native bridge injects into the remote
   page, plus the appended user-agent marker — deliberately NO `@capacitor/*`
   import, so this is safe in the Next.js web build and during SSR (returns false
   on the server). */

interface CapacitorGlobal {
  isNativePlatform?: () => boolean;
  getPlatform?: () => string;
}

function cap(): CapacitorGlobal | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as unknown as { Capacitor?: CapacitorGlobal }).Capacitor;
}

export function isNativeApp(): boolean {
  if (typeof window === "undefined") return false;
  if (cap()?.isNativePlatform?.()) return true;
  return /BlackVoltApp/.test(navigator.userAgent || "");
}

export function nativePlatform(): "ios" | "android" | null {
  const p = cap()?.getPlatform?.();
  return p === "ios" || p === "android" ? p : null;
}
