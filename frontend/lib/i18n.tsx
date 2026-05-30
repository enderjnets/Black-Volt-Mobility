"use client";

/**
 * Lightweight client-side i18n. Default language is English; Spanish is the
 * second option. The choice is persisted to localStorage and reflected on
 * <html lang>. `t(key)` looks the key up in the active dictionary, falls back to
 * English, then to the key itself. Add every new string to BOTH dictionaries.
 */
import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Lang = "en" | "es";

const STORAGE_KEY = "blackvolt-lang";

const EN: Record<string, string> = {
  "brand.name": "Black Volt Mobility",
  "brand.tagline": "Silent Power. Premium Arrival.",
  "nav.home": "Home",
  "nav.book": "Book a ride",
  "nav.dashboard": "Dashboard",
  "lang.label": "Language",
  "version.history": "Version history",
  "version.close": "Close",
  "home.hero.title": "Premium electric rides, on your schedule.",
  "home.hero.subtitle": "Airport transfers and private chauffeur service in a luxury electric SUV. Silent, spacious, and always on time.",
  "home.cta.book": "Book a ride",
  "home.cta.driver": "Driver dashboard",
  "home.soon": "Booking opens soon",
  "common.loading": "Loading…",
};

const ES: Record<string, string> = {
  "brand.name": "Black Volt Mobility",
  "brand.tagline": "Poder Silencioso. Llegada Premium.",
  "nav.home": "Inicio",
  "nav.book": "Reservar viaje",
  "nav.dashboard": "Panel",
  "lang.label": "Idioma",
  "version.history": "Historial de versiones",
  "version.close": "Cerrar",
  "home.hero.title": "Viajes eléctricos premium, en tu horario.",
  "home.hero.subtitle": "Traslados al aeropuerto y servicio de chofer privado en una SUV eléctrica de lujo. Silenciosa, amplia y siempre puntual.",
  "home.cta.book": "Reservar viaje",
  "home.cta.driver": "Panel del driver",
  "home.soon": "Las reservas abren pronto",
  "common.loading": "Cargando…",
};

const DICTS: Record<Lang, Record<string, string>> = { en: EN, es: ES };

interface I18nContextValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  locale: string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en"); // default English

  useEffect(() => {
    const saved = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    if (saved === "en" || saved === "es") setLangState(saved);
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, l);
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      let s = DICTS[lang][key] ?? EN[key] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
      }
      return s;
    },
    [lang],
  );

  const locale = lang === "es" ? "es-US" : "en-US";

  return (
    <I18nContext.Provider value={{ lang, setLang, t, locale }}>{children}</I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    return {
      lang: "en",
      setLang: () => {},
      t: (key, vars) => {
        let s = EN[key] ?? key;
        if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
        return s;
      },
      locale: "en-US",
    };
  }
  return ctx;
}
