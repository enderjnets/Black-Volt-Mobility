"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Icon } from "@/components/bv/Icon";
import { Button } from "@/components/bv/ui";
import { GoogleSignInButton } from "@/components/bv/web/GoogleSignInButton";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { useI18n } from "@/lib/i18n";
import { fetchMe, loginGoogle, loginPassword, logout } from "@/lib/auth";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";
const STAFF = new Set(["owner", "driver"]);

function LoginCard() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/dashboard";
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    const res = await loginPassword(pw);
    if (res.ok) {
      router.push(next);
    } else {
      setErr(t("auth.invalidPassword"));
      setBusy(false);
    }
  };

  // Google sign-in for the driver: only owner/driver emails (allow-listed on the
  // backend) may enter the dashboard. A passenger account is signed out here.
  const onGoogle = async (idToken: string) => {
    setBusy(true);
    setErr(null);
    const res = await loginGoogle(idToken);
    if (!res.ok) {
      setErr(t("auth.googleFailed"));
      setBusy(false);
      return;
    }
    const me = await fetchMe();
    if (me.authenticated && STAFF.has(me.role || "")) {
      router.push(next);
    } else {
      await logout();
      setErr(t("auth.notDriver"));
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--void)",
        padding: 20,
        position: "relative",
      }}
    >
      <div style={{ position: "absolute", top: 16, right: 20 }}>
        <LanguageSwitcher />
      </div>
      <div
        style={{
          width: "100%",
          maxWidth: 380,
          background: "var(--obsidian)",
          border: "1px solid var(--volt-border)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-volt)",
          padding: 30,
          textAlign: "center",
        }}
      >
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 14,
              background: "var(--obsidian-2)",
              border: "1px solid var(--volt-border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "var(--shadow-volt-sm)",
            }}
          >
            <Icon name="zap" size={26} color="var(--volt)" fill="var(--volt)" />
          </div>
        </div>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24, color: "var(--arctic)", margin: "0 0 6px" }}>
          {t("auth.driverLogin")}
        </h1>
        <p style={{ fontSize: 14, lineHeight: 1.5, color: "var(--silver)", margin: "0 0 22px" }}>{t("auth.driverSub")}</p>

        <div style={{ textAlign: "left", marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7 }}>{t("auth.password")}</div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              background: "var(--obsidian-3)",
              borderRadius: "var(--radius-md)",
              padding: "12px 14px",
              border: `1px solid ${err ? "var(--danger)" : "var(--line-strong)"}`,
            }}
          >
            <Icon name="shield-check" size={18} color="var(--silver)" />
            <input
              type="password"
              value={pw}
              autoFocus
              onChange={(e) => setPw(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="••••••••"
              style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--arctic)", fontSize: 14, fontFamily: "var(--font-sans)" }}
            />
          </div>
          {err && <div style={{ fontSize: 12, color: "var(--danger)", marginTop: 8 }}>{err}</div>}
        </div>

        <Button variant="solid" full size="lg" icon="zap" disabled={busy || !pw} onClick={submit}>
          {busy ? t("auth.signingin") : t("auth.signin")}
        </Button>

        {GOOGLE_CLIENT_ID && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "18px 0 14px" }}>
              <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
              <span style={{ fontSize: 11, color: "var(--fg3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
                {t("auth.or")}
              </span>
              <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
            </div>
            {busy ? (
              <div style={{ fontSize: 13, color: "var(--silver)", textAlign: "center" }}>{t("auth.googleSigningIn")}</div>
            ) : (
              <GoogleSignInButton clientId={GOOGLE_CLIENT_ID} onCredential={onGoogle} />
            )}
          </>
        )}
      </div>
      <div style={{ marginTop: 18, fontSize: 12, color: "var(--fg3)" }}>{t("brand.name")} · Denver / Aurora, CO</div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginCard />
    </Suspense>
  );
}
