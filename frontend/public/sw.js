/* Black Volt PWA service worker.
 *
 * Deliberately minimal: it exists to receive Web Push and open deep-links. It does
 * NOT cache HTML (a known footgun here — stale app shells) or intercept fetches, so
 * the site always loads fresh from the network/CDN. One file serves both PWAs; each
 * host (apex = client, app. = driver) registers it on its own origin, so relative
 * deep-links resolve to the right place. */

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// A fetch handler is required for Chrome to consider the app installable. We keep
// it a pure pass-through — no respondWith, so the browser fetches normally and we
// deliberately cache nothing (no stale app shell).
self.addEventListener("fetch", () => {});

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (e) {
    payload = { title: "Black Volt", body: event.data ? event.data.text() : "" };
  }
  const title = payload.title || "Black Volt";
  const options = {
    body: payload.body || "",
    icon: "/icons/icon-192.png",
    badge: "/icons/badge-72.png",
    tag: payload.tag || undefined,
    data: { url: payload.url || "/" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      // Focus an existing tab if one is already open; otherwise open a new one.
      for (const client of clients) {
        if ("focus" in client) {
          if ("navigate" in client) client.navigate(target).catch(() => {});
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    })
  );
});
