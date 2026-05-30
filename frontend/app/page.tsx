"use client";

import { Zap } from "lucide-react";

import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { VersionButton } from "@/components/ui/VersionButton";
import { useI18n } from "@/lib/i18n";

export default function Home() {
  const { t } = useI18n();
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-2">
          <Zap className="h-6 w-6 text-volt" fill="#00E5FF" />
          <span className="font-display text-lg font-bold tracking-wide text-arctic">
            {t("brand.name")}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <VersionButton />
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <div className="mb-6 flex items-center gap-2 rounded-full border border-volt/30 px-4 py-1 text-xs uppercase tracking-[0.2em] text-volt">
          <Zap className="h-3.5 w-3.5" fill="#00E5FF" />
          {t("brand.tagline")}
        </div>
        <h1 className="max-w-2xl font-display text-4xl font-bold leading-tight text-arctic sm:text-5xl">
          {t("home.hero.title")}
        </h1>
        <p className="mt-4 max-w-xl text-base text-silver">{t("home.hero.subtitle")}</p>

        <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row">
          <button
            disabled
            className="cursor-not-allowed rounded-lg bg-volt/20 px-6 py-3 font-medium text-volt"
            title={t("home.soon")}
          >
            {t("home.cta.book")}
          </button>
          <span className="text-xs text-silver/60">{t("home.soon")}</span>
        </div>
      </main>

      <footer className="px-5 py-4 text-center text-xs text-silver/50">
        © {t("brand.name")} · Denver / Aurora, CO
      </footer>
    </div>
  );
}
