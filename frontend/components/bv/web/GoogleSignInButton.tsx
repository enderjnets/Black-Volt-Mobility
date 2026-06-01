"use client";

import { useCallback, useEffect, useRef } from "react";

/* Real Google Identity Services button. Renders Google's official button and,
   on credential, hands the ID token up. Dormant unless NEXT_PUBLIC_GOOGLE_CLIENT_ID
   is set at build (see SignInModal, which falls back to a demo button). */

declare global {
  interface Window {
    google?: any;
  }
}

const GSI_SRC = "https://accounts.google.com/gsi/client";

export function GoogleSignInButton({
  clientId,
  onCredential,
}: {
  clientId: string;
  onCredential: (idToken: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cb = useCallback(onCredential, [onCredential]);

  useEffect(() => {
    let cancelled = false;
    const render = () => {
      if (cancelled || !window.google || !ref.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (resp: { credential?: string }) => resp.credential && cb(resp.credential),
      });
      ref.current.innerHTML = "";
      window.google.accounts.id.renderButton(ref.current, {
        theme: "filled_black",
        size: "large",
        type: "standard",
        text: "continue_with",
        shape: "rectangular",
        logo_alignment: "left",
        width: 320,
      });
    };
    if (window.google) {
      render();
      return;
    }
    let script = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
    if (!script) {
      script = document.createElement("script");
      script.src = GSI_SRC;
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
    }
    script.addEventListener("load", render);
    return () => {
      cancelled = true;
      script?.removeEventListener("load", render);
    };
  }, [clientId, cb]);

  return <div ref={ref} style={{ display: "flex", justifyContent: "center", minHeight: 44 }} />;
}
