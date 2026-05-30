"use client";

import { Globe } from "lucide-react";

import { useI18n } from "@/lib/i18n";

export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="flex items-center gap-1 text-xs" title={t("lang.label")}>
      <Globe className="h-4 w-4 text-silver" />
      <button
        onClick={() => setLang("en")}
        className={lang === "en" ? "font-semibold text-volt" : "text-silver hover:text-arctic"}
      >
        EN
      </button>
      <span className="text-silver/40">/</span>
      <button
        onClick={() => setLang("es")}
        className={lang === "es" ? "font-semibold text-volt" : "text-silver hover:text-arctic"}
      >
        ES
      </button>
    </div>
  );
}
