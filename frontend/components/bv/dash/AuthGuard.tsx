"use client";

import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

import { Icon } from "../Icon";
import { AgreementGate } from "../AgreementGate";
import { useI18n } from "@/lib/i18n";
import { fetchMe, type Me } from "@/lib/auth";

const STAFF = new Set(["owner", "driver"]);

/** Gates the driver dashboard. When the backend has AUTH_ENABLED, a non-staff
 *  visitor is redirected to /login. In open mode (dev), it renders through. */
export function AuthGuard({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<"checking" | "ok">("checking");
  const [me, setMe] = useState<Me | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let alive = true;
    fetchMe().then((me) => {
      if (!alive) return;
      const allowed = !me.auth_enabled || (me.authenticated && STAFF.has(me.role || ""));
      if (allowed) {
        setMe(me);
        setState("ok");
      } else router.replace(`/login?next=${encodeURIComponent(pathname || "/dashboard")}`);
    });
    return () => {
      alive = false;
    };
  }, [router, pathname, refresh]);

  if (state === "checking") {
    return (
      <div
        style={{
          minHeight: "100dvh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 14,
          background: "var(--void)",
        }}
      >
        <Icon name="zap" size={30} color="var(--volt)" fill="var(--volt)" />
        <span style={{ fontSize: 13, color: "var(--silver)", fontFamily: "var(--font-sans)" }}>{t("auth.checking")}</span>
      </div>
    );
  }
  if (me?.agreements_pending && me.agreements_pending.length > 0) {
    return <AgreementGate pending={me.agreements_pending} onComplete={() => setRefresh((n) => n + 1)} />;
  }
  return <>{children}</>;
}
