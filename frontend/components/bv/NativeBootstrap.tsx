"use client";

/* Native-only bootstrap. On the web this renders nothing and runs no effects
   (isNativeApp() is false). Inside the Capacitor shell it: installs the fetch
   interceptor (bearer + X-BV-Native), loads any stored token, warms up SocialLogin,
   and — if already signed in — (re)registers the device for FCM push. */
import { useEffect } from "react";
import { isNativeApp } from "@/lib/native";
import { installNativeFetch } from "@/lib/nativeFetch";
import { loadToken, getToken } from "@/lib/nativeToken";
import { initSocialLogin } from "@/lib/nativeAuth";
import { registerFcm } from "@/lib/nativePush";

export default function NativeBootstrap() {
  useEffect(() => {
    if (!isNativeApp()) return;
    installNativeFetch();
    void (async () => {
      await loadToken();
      await initSocialLogin();
      if (getToken()) await registerFcm();
    })();
  }, []);
  return null;
}
