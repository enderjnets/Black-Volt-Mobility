// Black Volt Mobility — native wrapper for the CLIENT app. It loads the live
// site (server.url) rather than bundling a static export: the site is SSR with
// /api rewrites, so a wrapper keeps one deploy pipeline and fixes ship without a
// store review. Capacitor still injects its bridge into the remote page, so the
// native plugins (Google Sign-In, Push, App) work.
//
// Dev: set CAP_SERVER_URL=http://<LAN-IP>:3005 to point at a local stack. NEVER
// run real bookings against production (Square is LIVE) — use the dev stack.
//
// (Plain JS config, not .ts: Capacitor 8's TS-config loader breaks with current
// TypeScript, and we need process.env which JSON can't read.)

/** @type {import('@capacitor/cli').CapacitorConfig} */
const config = {
  appId: 'com.blackvoltmobility.app',
  appName: 'Black Volt',
  webDir: 'www',
  server: {
    url: process.env.CAP_SERVER_URL || 'https://blackvoltmobility.com',
    androidScheme: 'https',
    allowNavigation: [
      'blackvoltmobility.com',
      '*.blackvoltmobility.com',
      // Square Web Payments 3-D Secure can redirect top-level.
      '*.squareup.com',
      '*.squarecdn.com',
      // Google Sign-In / consent screens.
      'accounts.google.com',
      '*.google.com',
    ],
  },
  android: {
    allowMixedContent: false,
    // Dark WebView background so no white shows at the edges / on overscroll
    // before or around the (already-dark) page.
    backgroundColor: '#0A0A0F',
    // Lets the site detect the native app (belt-and-braces with
    // Capacitor.isNativePlatform()).
    appendUserAgent: 'BlackVoltApp',
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1200,
      launchAutoHide: true,
      backgroundColor: '#0A0A0F',
      showSpinner: false,
    },
    StatusBar: {
      // Solid dark status bar with light icons, not overlaying the WebView.
      style: 'DARK',
      backgroundColor: '#0A0A0F',
      overlaysWebView: false,
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
};

module.exports = config;
