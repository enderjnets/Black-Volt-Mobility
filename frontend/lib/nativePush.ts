/* Native FCM push registration. Asks for the OS notification permission, registers the
   device with FCM through the Capacitor PushNotifications plugin, and mirrors the
   resulting token to the backend as an `fcm` push subscription (the fetch interceptor
   adds the bearer + native header). Call this only for a signed-in user — the
   /push/subscribe endpoint needs a valid session to file the token under the client. */
import { pushPlugin } from "./nativeBridge";

let registered = false;

export async function registerFcm(): Promise<void> {
  const push = pushPlugin();
  if (!push || registered) return;
  registered = true;
  try {
    let perm = await push.checkPermissions();
    if (perm.receive === "prompt" || perm.receive === "prompt-with-rationale") {
      perm = await push.requestPermissions();
    }
    if (perm.receive !== "granted") {
      registered = false;
      return;
    }

    await push.addListener("registration", (data) => {
      const value = (data as { value?: string })?.value;
      if (!value) return;
      fetch("/api/v1/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: value, platform: "fcm" }),
      }).catch(() => {
        /* backend will re-prompt on next boot */
      });
    });
    await push.addListener("registrationError", () => {
      /* logged natively; nothing actionable in the WebView */
    });

    await push.register();
  } catch {
    registered = false;
  }
}
