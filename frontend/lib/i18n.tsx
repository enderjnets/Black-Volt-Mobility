"use client";

/**
 * Lightweight client-side i18n. Default language is English; Spanish is the
 * second option. Persisted to localStorage and reflected on <html lang>.
 * `t(key)` looks up the active dictionary, falls back to English, then the key.
 * Add every new string to BOTH dictionaries.
 */
import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Lang = "en" | "es";

const STORAGE_KEY = "blackvolt-lang";

const EN: Record<string, string> = {
  "brand.name": "Black Volt Mobility",
  "brand.tagline": "Silent Power. Premium Arrival.",
  "lang.label": "Language",
  "version.history": "Version history",
  "version.close": "Close",
  "common.loading": "Loading…",
  "common.soon": "Booking opens soon",
  "common.back": "Back",
  // nav
  "nav.home": "Home",
  "nav.book": "Book a ride",
  "nav.fleet": "The Fleet",
  "nav.driver": "Your Driver",
  "nav.trips": "My Trips",
  "nav.account": "Account",
  "nav.dashboard": "Dashboard",
  // landing
  "home.hero.title": "Premium electric rides, on your schedule.",
  "home.hero.subtitle":
    "Airport transfers and private chauffeur service in a luxury electric SUV. Silent, spacious, and always on time.",
  "home.cta.book": "Book a ride",
  "home.cta.driver": "Driver dashboard",
  "home.f1.t": "Silent EV ride",
  "home.f1.d": "A whisper-quiet Kia EV9 — zero emissions, full comfort.",
  "home.f2.t": "Flight-aware pickups",
  "home.f2.d": "We track your flight and adjust pickup for delays automatically.",
  "home.f3.t": "Fixed, upfront pricing",
  "home.f3.d": "See the route and the exact fare before you confirm. No surge.",
  "home.fleet.eyebrow": "The Fleet",
  "home.fleet.title": "One car. Done right.",
  "home.fleet.body":
    "A blacked-out Kia EV9 — three rows, captain's chairs, climate per seat, and a silent ride from curb to gate.",
  // booking
  "book.title": "Book your ride",
  "book.from": "Pickup",
  "book.to": "Dropoff",
  "book.from.ph": "Pickup address",
  "book.to.ph": "Denver Intl (DEN)",
  "book.when": "When",
  "book.now": "Now",
  "book.schedule": "Schedule",
  "book.pax": "Passengers",
  "book.review": "Review route",
  "book.fare": "Estimated fare",
  "book.distance": "Distance",
  "book.eta": "Pickup ETA",
  "book.pay": "Confirm & pay",
  "book.paybtn": "Pay with Square",
  "book.silent": "Silent Power. Premium Arrival.",
  "book.confirmed": "Ride confirmed",
  "book.confirmed.sub": "Your driver Ender will arrive in a black Kia EV9.",
  "book.another": "Book another",
  // profile
  "profile.verified": "Verified driver",
  "profile.book": "Book with Ender",
  "profile.scan": "Scan to save",
  "profile.scan.sub": "Add Ender to your contacts and rides.",
  "profile.rides": "Rides",
  "profile.rating": "Rating",
  "profile.years": "On the road",
  // trips
  "trips.title": "Your trips",
  "trips.upcoming": "Upcoming",
  "trips.past": "Past",
  "trips.enroute": "Driver en route",
  "trips.arriving": "Arriving in",
  "trips.driver": "Your driver",
  "trips.message": "Message",
  "trips.call": "Call",
  "trips.flight": "Flight",
  "trips.ontime": "On time",
  "trips.delayed": "Delayed",
  "trips.gate": "Gate",
  "trips.lands": "Lands",
  "trips.tracking": "Live tracking",
  "trips.none": "No past trips yet.",
  // chat
  "chat.title": "Black Volt Assistant",
  "chat.sub": "Ask about rides, fares or your trip",
  "chat.ph": "Type a message…",
  "chat.q1": "Where's my driver?",
  "chat.q2": "Change pickup time",
  "chat.q3": "Get a fare estimate",
  "chat.greet": "Hi Alex — your EV9 is 6 minutes away. Anything you need before pickup?",
  // auth
  "auth.signin": "Sign in",
  "auth.signout": "Sign out",
  "auth.google": "Continue with Google",
  "auth.signingin": "Signing in…",
  "auth.welcome": "Welcome back",
  "auth.subtitle": "Sign in to book rides, save your addresses and track every trip.",
  "auth.terms": "By continuing you agree to our Terms & Privacy Policy.",
  "auth.phone": "Continue with phone (SMS)",
  "auth.or": "or",
  // account
  "acct.title": "Your account",
  "acct.profile": "Profile",
  "acct.member": "Member since",
  "acct.addresses": "Saved addresses",
  "acct.add": "Add address",
  "acct.default": "Default",
  "acct.payment": "Payment method",
  "acct.lang": "Language",
  "acct.home": "Home",
  "acct.work": "Work",
  "acct.edit": "Edit",
  "acct.notif": "Notifications",
  "acct.sms": "SMS updates",
  "acct.email": "Email receipts",
  "acct.prefs": "Preferences",
};

const ES: Record<string, string> = {
  "brand.name": "Black Volt Mobility",
  "brand.tagline": "Poder Silencioso. Llegada Premium.",
  "lang.label": "Idioma",
  "version.history": "Historial de versiones",
  "version.close": "Cerrar",
  "common.loading": "Cargando…",
  "common.soon": "Las reservas abren pronto",
  "common.back": "Atrás",
  "nav.home": "Inicio",
  "nav.book": "Reservar viaje",
  "nav.fleet": "La Flota",
  "nav.driver": "Tu Chofer",
  "nav.trips": "Mis Viajes",
  "nav.account": "Cuenta",
  "nav.dashboard": "Panel",
  "home.hero.title": "Viajes eléctricos premium, en tu horario.",
  "home.hero.subtitle":
    "Traslados al aeropuerto y servicio de chofer privado en una SUV eléctrica de lujo. Silenciosa, amplia y siempre puntual.",
  "home.cta.book": "Reservar viaje",
  "home.cta.driver": "Panel del driver",
  "home.f1.t": "Viaje eléctrico silencioso",
  "home.f1.d": "Un Kia EV9 silencioso — cero emisiones, máximo confort.",
  "home.f2.t": "Recogidas según tu vuelo",
  "home.f2.d": "Seguimos tu vuelo y ajustamos la recogida ante retrasos.",
  "home.f3.t": "Precio fijo por adelantado",
  "home.f3.d": "Mira la ruta y la tarifa exacta antes de confirmar. Sin recargos.",
  "home.fleet.eyebrow": "La Flota",
  "home.fleet.title": "Un auto. Bien hecho.",
  "home.fleet.body":
    "Un Kia EV9 negro — tres filas, asientos capitán, clima por asiento y un viaje silencioso de la acera a la puerta.",
  "book.title": "Reserva tu viaje",
  "book.from": "Recogida",
  "book.to": "Destino",
  "book.from.ph": "Dirección de recogida",
  "book.to.ph": "Denver Intl (DEN)",
  "book.when": "Cuándo",
  "book.now": "Ahora",
  "book.schedule": "Programar",
  "book.pax": "Pasajeros",
  "book.review": "Revisar ruta",
  "book.fare": "Tarifa estimada",
  "book.distance": "Distancia",
  "book.eta": "ETA de recogida",
  "book.pay": "Confirmar y pagar",
  "book.paybtn": "Pagar con Square",
  "book.silent": "Poder Silencioso. Llegada Premium.",
  "book.confirmed": "Viaje confirmado",
  "book.confirmed.sub": "Tu chofer Ender llegará en un Kia EV9 negro.",
  "book.another": "Reservar otro",
  "profile.verified": "Chofer verificado",
  "profile.book": "Reservar con Ender",
  "profile.scan": "Escanea para guardar",
  "profile.scan.sub": "Agrega a Ender a tus contactos y viajes.",
  "profile.rides": "Viajes",
  "profile.rating": "Calificación",
  "profile.years": "En la ruta",
  "trips.title": "Tus viajes",
  "trips.upcoming": "Próximos",
  "trips.past": "Anteriores",
  "trips.enroute": "Chofer en camino",
  "trips.arriving": "Llega en",
  "trips.driver": "Tu chofer",
  "trips.message": "Mensaje",
  "trips.call": "Llamar",
  "trips.flight": "Vuelo",
  "trips.ontime": "A tiempo",
  "trips.delayed": "Retrasado",
  "trips.gate": "Puerta",
  "trips.lands": "Aterriza",
  "trips.tracking": "Seguimiento en vivo",
  "trips.none": "Aún no hay viajes anteriores.",
  "chat.title": "Asistente Black Volt",
  "chat.sub": "Pregunta por viajes, tarifas o tu trayecto",
  "chat.ph": "Escribe un mensaje…",
  "chat.q1": "¿Dónde está mi chofer?",
  "chat.q2": "Cambiar hora de recogida",
  "chat.q3": "Estimar una tarifa",
  "chat.greet": "Hola Alex — tu EV9 está a 6 minutos. ¿Necesitas algo antes de la recogida?",
  "auth.signin": "Iniciar sesión",
  "auth.signout": "Cerrar sesión",
  "auth.google": "Continuar con Google",
  "auth.signingin": "Iniciando sesión…",
  "auth.welcome": "Bienvenido de nuevo",
  "auth.subtitle": "Inicia sesión para reservar, guardar tus direcciones y seguir cada viaje.",
  "auth.terms": "Al continuar aceptas nuestros Términos y Política de Privacidad.",
  "auth.phone": "Continuar con teléfono (SMS)",
  "auth.or": "o",
  "acct.title": "Tu cuenta",
  "acct.profile": "Perfil",
  "acct.member": "Miembro desde",
  "acct.addresses": "Direcciones guardadas",
  "acct.add": "Agregar dirección",
  "acct.default": "Predeterminada",
  "acct.payment": "Método de pago",
  "acct.lang": "Idioma",
  "acct.home": "Casa",
  "acct.work": "Trabajo",
  "acct.edit": "Editar",
  "acct.notif": "Notificaciones",
  "acct.sms": "Avisos por SMS",
  "acct.email": "Recibos por correo",
  "acct.prefs": "Preferencias",
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
