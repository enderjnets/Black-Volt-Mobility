"use client";

/* Black Volt Mobility — Add reservation (Manual + Smart/AI screenshot modes).
   Ported from the design system's dashboard kit. Smart mode reads a screenshot
   via window.claude vision when available, else a believable sample extraction. */
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Icon } from "../Icon";
import { Button, Pill } from "../ui";
import { SuggestionDropdown, useAddressSuggest } from "../AddressAutocomplete";
import { BVDatePicker, BVTimePicker } from "../DateTimePicker";
import { buildScheduledAt, normDate, normTime } from "@/lib/datetime";
import { ClientSuggestionDropdown, useClientSuggest } from "../ClientAutocomplete";
import { useI18n } from "@/lib/i18n";
import { getClientDetail, inferRoute, type ClientLite } from "@/lib/dashboard";
import { createRide, getQuote } from "@/lib/booking";
import { extractReservations, hasAnyField, SmartError } from "@/lib/smart";

const SMART_MAX_IMAGES = 6;

type Shot = { file: File; url: string };

type Form = Record<string, string>;
const BV_BLANK: Form = {
  name: "", phone: "", lang: "EN", pickup: "", dropoff: "", date: "", time: "",
  flight: "", passengers: "", fare: "", notes: "",
  // Set when the name is picked from an existing client so the ride links to that
  // client; cleared as soon as the name is edited by hand (→ get-or-create).
  client_id: "",
};
const BV_REQUIRED = ["name", "phone", "pickup", "dropoff", "date", "time", "fare"];

const BV_T: Record<string, any> = {
  en: {
    manual: "Manual", smart: "Smart", smartTag: "AI",
    modeManualSub: "Type the details yourself.",
    modeSmartSub: "Paste a screenshot — AI fills it in.",
    secClient: "Client", secTrip: "Trip", secExtra: "Flight & details",
    name: "Full name", phone: "Phone", prefLang: "Preferred language",
    pickup: "Pickup", dropoff: "Drop-off", date: "Date", time: "Pickup time",
    flight: "Flight number", passengers: "Passengers", fare: "Fare", notes: "Notes",
    namePh: "e.g. Alex Rivera", phonePh: "+1 303 555 0100",
    pickupPh: "Hotel, address or DEN", dropoffPh: "Destination or DEN",
    datePh: "Jun 14", timePh: "14:20", flightPh: "UA 2293", paxPh: "1",
    notesPh: "Luggage, child seat, gate, special requests…",
    suggested: "Suggested · DEN flat rate",
    suggestedQuote: "Suggested · live quote",
    previewTitle: "Reservation preview", previewEmpty: "Fill in the form to preview the ride.",
    create: "Create reservation", creating: "Creating…",
    squareNote: "Payment collected on card via Square.",
    needRequired: "Complete the required fields to continue.",
    createErr: "Couldn't create the reservation — check the fields and try again.",
    errDateTime: "Please set a valid date and time for the ride.",
    dropTitle: "Drop, paste or upload screenshots",
    dropSub: "One or several SMS, WhatsApp, email or notes from the client — AI reads the details.",
    dropBtn: "Choose images", paste: "or press ⌘V / Ctrl+V to paste",
    sample: "Try a sample", change: "Replace", extract: "Extract with AI",
    addMore: "Add more", removeImg: "Remove", maxImgs: (n: number) => `Up to ${n} screenshots.`,
    shotsCount: (n: number) => `${n} ${n === 1 ? "screenshot" : "screenshots"}`,
    demoNote: "Demo mode — set the vision key on the server for real extraction.",
    err_unsupported_image_type: "That image format isn't supported — use a PNG or JPG screenshot.",
    err_image_too_large: "That image is too large — try a screenshot under 10 MB.",
    err_decode_failed: "Couldn't read that image (HEIC?) — convert it to PNG or JPG and retry.",
    err_service: "Couldn't reach the AI service — try again, or fill the form manually.",
    err_too_many: "Too many screenshots — remove some, then add more.",
    err_not_image: "That file isn't an image — upload a PNG or JPG screenshot.",
    startOver: "Start over",
    reservationN: (n: number) => `Reservation ${n}`,
    readyTag: "Ready",
    missingTag: (n: number) => `${n} missing`,
    createdTag: "Created",
    createThis: "Create this ride",
    createAll: (n: number) => `Create all ready (${n})`,
    discard: "Discard",
    queueHint: "Review each reservation, then create.",
    multiDoneTitle: (n: number) => `${n} rides created`,
    multiDoneSub: "Confirmation messages are ready to send.",
    noReadNote: "Couldn't read the details from the image — add them manually below.",
    scanning: "Reading the screenshots…", scanningSub: "Pulling out the reservation details.",
    scanningN: (n: number) => `Reading ${n} ${n === 1 ? "screenshot" : "screenshots"}…`,
    foundOf: (a: number, b: number) => `AI found ${a} of ${b} details.`,
    allGood: "All details captured — review and create.",
    confirm: (n: number) => `Confirm ${n} highlighted ${n === 1 ? "field" : "fields"}.`,
    missingHint: "Couldn't read this — please add it",
    aiHint: "Read from screenshot",
    doneTitle: "Reservation created", doneSub: "Added to your rides.",
    addAnother: "Add another", viewRides: "View in rides",
    confTitle: "Confirmation message", confSub: "Auto-generated for the client.",
    sendQ: "How would you like to send it to the client?",
    sendAuto: "Send by SMS now", sendManual: "Send manually",
    sentAuto: "Confirmation sent by SMS", autoNote: "Delivered automatically to",
    manualHint: "Copy the message and paste it into your SMS or WhatsApp app.",
    copy: "Copy message", copied: "Copied to clipboard", to: "To",
    another: "Choose another way",
    langEN: "English", langES: "Spanish",
    backCapture: "Back to screenshot",
    swap: "Swap",
  },
  es: {
    manual: "Manual", smart: "Inteligente", smartTag: "IA",
    modeManualSub: "Escribe los datos tú mismo.",
    modeSmartSub: "Pega una captura — la IA la completa.",
    secClient: "Cliente", secTrip: "Viaje", secExtra: "Vuelo y detalles",
    name: "Nombre completo", phone: "Teléfono", prefLang: "Idioma preferido",
    pickup: "Recogida", dropoff: "Destino", date: "Fecha", time: "Hora de recogida",
    flight: "Número de vuelo", passengers: "Pasajeros", fare: "Tarifa", notes: "Notas",
    namePh: "ej. Alex Rivera", phonePh: "+1 303 555 0100",
    pickupPh: "Hotel, dirección o DEN", dropoffPh: "Destino o DEN",
    datePh: "14 jun", timePh: "14:20", flightPh: "UA 2293", paxPh: "1",
    notesPh: "Equipaje, silla de bebé, puerta, peticiones…",
    suggested: "Sugerido · tarifa fija DEN",
    suggestedQuote: "Sugerido · cotización en vivo",
    previewTitle: "Vista previa de la reserva", previewEmpty: "Completa el formulario para ver el viaje.",
    create: "Crear reserva", creating: "Creando…",
    squareNote: "El pago se cobra con tarjeta vía Square.",
    needRequired: "Completa los campos obligatorios para continuar.",
    createErr: "No se pudo crear la reserva — revisa los campos e intenta de nuevo.",
    errDateTime: "Indica una fecha y hora válidas para el viaje.",
    dropTitle: "Arrastra, pega o sube capturas",
    dropSub: "Uno o varios SMS, WhatsApp, correos o notas del cliente — la IA lee los datos.",
    dropBtn: "Elegir imágenes", paste: "o pulsa ⌘V / Ctrl+V para pegar",
    sample: "Probar un ejemplo", change: "Reemplazar", extract: "Extraer con IA",
    addMore: "Añadir más", removeImg: "Quitar", maxImgs: (n: number) => `Hasta ${n} capturas.`,
    shotsCount: (n: number) => `${n} ${n === 1 ? "captura" : "capturas"}`,
    demoNote: "Modo demo — configura la clave de visión en el servidor para extracción real.",
    err_unsupported_image_type: "Ese formato de imagen no es compatible — usa una captura PNG o JPG.",
    err_image_too_large: "Esa imagen es muy grande — usa una captura de menos de 10 MB.",
    err_decode_failed: "No pude leer esa imagen (¿HEIC?) — conviértela a PNG o JPG e intenta de nuevo.",
    err_service: "No pude contactar el servicio de IA — intenta de nuevo o llena el formulario a mano.",
    err_too_many: "Demasiadas capturas — quita algunas y agrega más.",
    err_not_image: "Ese archivo no es una imagen — sube una captura PNG o JPG.",
    startOver: "Empezar de nuevo",
    reservationN: (n: number) => `Reserva ${n}`,
    readyTag: "Lista",
    missingTag: (n: number) => `Faltan ${n}`,
    createdTag: "Creada",
    createThis: "Crear este viaje",
    createAll: (n: number) => `Crear todas las listas (${n})`,
    discard: "Descartar",
    queueHint: "Revisa cada reserva y créala.",
    multiDoneTitle: (n: number) => `${n} viajes creados`,
    multiDoneSub: "Los mensajes de confirmación están listos para enviar.",
    noReadNote: "No pude leer los datos de la imagen — agrégalos a mano abajo.",
    scanning: "Leyendo las capturas…", scanningSub: "Extrayendo los datos de la reserva.",
    scanningN: (n: number) => `Leyendo ${n} ${n === 1 ? "captura" : "capturas"}…`,
    foundOf: (a: number, b: number) => `La IA encontró ${a} de ${b} datos.`,
    allGood: "Todos los datos capturados — revisa y crea.",
    confirm: (n: number) => `Confirma ${n} campo${n === 1 ? "" : "s"} resaltado${n === 1 ? "" : "s"}.`,
    missingHint: "No se pudo leer — por favor agrégalo",
    aiHint: "Leído de la captura",
    doneTitle: "Reserva creada", doneSub: "Añadida a tus viajes.",
    addAnother: "Añadir otra", viewRides: "Ver en viajes",
    confTitle: "Mensaje de confirmación", confSub: "Generado automáticamente para el cliente.",
    sendQ: "¿Cómo quieres enviárselo al cliente?",
    sendAuto: "Enviar por SMS ahora", sendManual: "Enviar manualmente",
    sentAuto: "Confirmación enviada por SMS", autoNote: "Entregada automáticamente a",
    manualHint: "Copia el mensaje y pégalo en tu app de SMS o WhatsApp.",
    copy: "Copiar mensaje", copied: "Copiado al portapapeles", to: "Para",
    another: "Elegir otra forma",
    langEN: "Inglés", langES: "Español",
    backCapture: "Volver a la captura",
    swap: "Invertir",
  },
};

function bvConfirmationMsg(f: Form): string {
  const es = String(f.lang || "EN").toUpperCase() === "ES";
  const first = (f.name || "").trim().split(/\s+/)[0] || "";
  const when = [f.date, f.time].filter(Boolean).join(" · ");
  const route = `${f.pickup || "—"} → ${f.dropoff || "—"}`;
  const flight = f.flight ? (es ? `Vuelo ${f.flight}` : `Flight ${f.flight}`) : "";
  const pax = f.passengers ? (es ? `${f.passengers} pasajero(s)` : `${f.passengers} passenger(s)`) : "";
  const extra = [flight, pax].filter(Boolean).join(" · ");
  const fare = f.fare ? (es ? `Tarifa $${f.fare}, pago con tarjeta (Square).` : `Fare $${f.fare}, paid by card (Square).`) : "";
  if (es) {
    return `Hola${first ? " " + first : ""}, tu viaje con Black Volt Mobility está confirmado.\n\n${when}\n${route}${extra ? "\n" + extra : ""}${fare ? "\n" + fare : ""}\n\nTu Kia EV9 negro llegará puntual. Responde a este mensaje si algo cambia.\n— Black Volt Mobility · Poder silencioso, llegada premium.`;
  }
  return `Hi${first ? " " + first : ""}, your Black Volt Mobility ride is confirmed.\n\n${when}\n${route}${extra ? "\n" + extra : ""}${fare ? "\n" + fare : ""}\n\nYour blacked-out Kia EV9 will arrive on time. Reply to this message if anything changes.\n— Black Volt Mobility · Silent power, premium arrival.`;
}

function bvSuggestFare(pickup: string, dropoff: string): number | null {
  const s = `${pickup || ""} ${dropoff || ""}`.toLowerCase();
  if (/\bden\b|airport|aeropuerto|intl|international/.test(s)) return 74;
  return null;
}

// Offline sample for "Try a sample" — the real extraction runs server-side
// (MiniMax-M3 vision) via /api/v1/rides/extract.
const BV_SAMPLE_EXTRACTION: Record<string, unknown> = {
  name: "Daniel Ortega", phone: null, lang: "ES",
  pickup: "The Crawford Hotel", dropoff: "Denver Intl (DEN)",
  date: "Jun 14", time: "06:30", flight: "UA 1455",
  passengers: 2, fare: null, notes: "2 maletas grandes",
};

function fieldState(key: string, form: Form, aiFields: Record<string, boolean>, mode: string, aiRan: boolean) {
  const empty = !String(form[key] || "").trim();
  const required = BV_REQUIRED.includes(key);
  if (mode === "smart" && aiRan && required && empty) return "missing";
  if (mode === "smart" && aiRan && aiFields[key] && !empty) return "ai";
  return "normal";
}

export function AddRide() {
  const { lang } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = BV_T[lang] || BV_T.en;
  const [mode, setMode] = useState<"manual" | "smart">("manual");
  const [smartStage, setSmartStage] = useState<"capture" | "scanning" | "form">("capture");
  type Draft = {
    form: Form;
    aiFields: Record<string, boolean>;
    createdId: number | null;
    createErr: string | null;
  };
  const blankDraft = (): Draft => ({
    form: { ...BV_BLANK },
    aiFields: {},
    createdId: null,
    createErr: null,
  });

  const [drafts, setDrafts] = useState<Draft[]>([blankDraft()]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [aiRan, setAiRan] = useState(false);
  const [shots, setShots] = useState<Shot[]>([]);
  const [smartDemo, setSmartDemo] = useState(false);
  const [smartErr, setSmartErr] = useState<string | null>(null);
  const [noRead, setNoRead] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [suggested, setSuggested] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  // The form editor always operates on the active draft. Manual mode = one draft;
  // a Smart scan can yield several (one per detected reservation).
  const active = drafts[activeIdx] ?? drafts[0];
  const form = active.form;
  const aiFields = active.aiFields;
  const setForm = (updater: Form | ((f: Form) => Form)) =>
    setDrafts((ds) =>
      ds.map((d, i) =>
        i === activeIdx
          ? {
              ...d,
              form:
                typeof updater === "function" ? (updater as (f: Form) => Form)(d.form) : updater,
            }
          : d,
      ),
    );
  const patchDraft = (idx: number, p: Partial<Draft>) =>
    setDrafts((ds) => ds.map((d, i) => (i === idx ? { ...d, ...p } : d)));

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const addFiles = (files: FileList | File[]) => {
    const arr = Array.from(files);
    const imgs = arr.filter((f) => f.type.startsWith("image/"));
    const room = SMART_MAX_IMAGES - shots.length;
    if (room <= 0) {
      setSmartErr("err_too_many");
      return;
    }
    const accepted = imgs.slice(0, room);
    setShots((prev) => {
      const r = SMART_MAX_IMAGES - prev.length;
      if (r <= 0) return prev;
      return [
        ...prev,
        ...accepted.slice(0, r).map((file) => ({ file, url: URL.createObjectURL(file) })),
      ];
    });
    // Tell the driver why some files didn't land, instead of silently dropping them.
    if (imgs.length > room) setSmartErr("err_too_many");
    else if (imgs.length < arr.length) setSmartErr("err_not_image");
    else setSmartErr(null);
  };
  const removeShot = (i: number) =>
    setShots((prev) => {
      const s = prev[i];
      if (s) URL.revokeObjectURL(s.url);
      return prev.filter((_, j) => j !== i);
    });
  const clearShots = () =>
    setShots((prev) => {
      prev.forEach((s) => URL.revokeObjectURL(s.url));
      return [];
    });
  const reset = () => {
    setDrafts([blankDraft()]);
    setActiveIdx(0);
    setAiRan(false);
    clearShots();
    setSmartDemo(false);
    setSmartErr(null);
    setNoRead(false);
    setSubmitting(false);
    setSuggested(null);
    setSmartStage("capture");
  };

  // Prefill from "New ride for this client" (Clients → client detail). Runs once.
  useEffect(() => {
    const name = searchParams.get("name");
    const phone = searchParams.get("phone");
    const ql = searchParams.get("lang");
    if (!name && !phone && !ql) return;
    setForm((f) => ({
      ...f,
      ...(name ? { name } : {}),
      ...(phone ? { phone } : {}),
      ...(ql ? { lang: ql.toUpperCase() === "ES" ? "ES" : "EN" } : {}),
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Live fare suggestion from the backend (Google Maps route + pricing engine).
  // Debounced; the static heuristic stays as an instant fallback.
  useEffect(() => {
    const pickup = form.pickup.trim();
    const dropoff = form.dropoff.trim();
    if (!pickup || !dropoff) {
      setSuggested(null);
      return;
    }
    let alive = true;
    const id = setTimeout(() => {
      getQuote({ pickup, dropoff, pax: form.passengers ? Number(form.passengers) : null })
        .then((q) => {
          if (alive) setSuggested(Math.round(q.total));
        })
        .catch(() => {
          if (alive) setSuggested(null);
        });
    }, 450);
    return () => {
      alive = false;
      clearTimeout(id);
    };
  }, [form.pickup, form.dropoff, form.passengers]);

  // Best available fare suggestion: live quote → heuristic flat → none.
  const fareHint = suggested ?? bvSuggestFare(form.pickup, form.dropoff);

  // Persist the reservation, then show the confirmation screen. A backend error
  // still advances to the success view (the confirmation SMS is the artifact).
  const rideInputFrom = (f: Form, scheduledAt: string) => ({
    pickup: f.pickup,
    dropoff: f.dropoff,
    pax: f.passengers ? Number(f.passengers) : null,
    scheduled_at: scheduledAt,
    flight_number: f.flight || null,
    lang: (f.lang || "EN").toUpperCase(),
    notes: f.notes || null,
    passenger_name: f.name || null,
    passenger_phone: f.phone || null,
    client_id: f.client_id ? Number(f.client_id) : null,
    fare_override: f.fare ? Number(f.fare) : null,
    confirm: true,
  });

  // Persist one draft (the active one by default). The result lives on the draft
  // (createdId / createErr) so the queue can show per-reservation status.
  const submit = async (idx: number = activeIdx) => {
    if (submitting) return;
    const d = drafts[idx];
    if (!d || d.createdId != null) return;
    // Never save a ride without a usable scheduled time — that's what kept rides
    // off the calendar. Block early with a clear message instead of failing silently.
    const scheduledAt = buildScheduledAt(d.form.date, d.form.time);
    if (!scheduledAt) {
      patchDraft(idx, { createErr: t.errDateTime });
      return;
    }
    setSubmitting(true);
    patchDraft(idx, { createErr: null });
    try {
      const res = await createRide(rideInputFrom(d.form, scheduledAt));
      if (res && typeof res.id === "number") patchDraft(idx, { createdId: res.id, createErr: null });
      else patchDraft(idx, { createErr: t.createErr });
    } catch (e) {
      patchDraft(idx, { createErr: e instanceof Error && e.message ? e.message : t.createErr });
    } finally {
      setSubmitting(false);
    }
  };

  // Create every complete, not-yet-created draft in one pass; incomplete ones stay
  // flagged in the queue for the driver to finish.
  const createAllReady = async () => {
    if (submitting) return;
    setSubmitting(true);
    const snapshot = drafts;
    const updates: Record<number, Partial<Draft>> = {};
    for (let i = 0; i < snapshot.length; i++) {
      const d = snapshot[i];
      if (d.createdId != null) continue;
      if (BV_REQUIRED.some((k) => !String(d.form[k] || "").trim())) continue;
      const scheduledAt = buildScheduledAt(d.form.date, d.form.time);
      if (!scheduledAt) {
        updates[i] = { createErr: t.errDateTime };
        continue;
      }
      try {
        const res = await createRide(rideInputFrom(d.form, scheduledAt));
        updates[i] =
          res && typeof res.id === "number"
            ? { createdId: res.id, createErr: null }
            : { createErr: t.createErr };
      } catch (e) {
        updates[i] = { createErr: e instanceof Error && e.message ? e.message : t.createErr };
      }
    }
    setDrafts((ds) => ds.map((d, i) => (updates[i] ? { ...d, ...updates[i] } : d)));
    setSubmitting(false);
  };

  const discardDraft = (idx: number) => {
    setDrafts((ds) => (ds.length <= 1 ? ds : ds.filter((_, i) => i !== idx)));
    setActiveIdx((cur) => (idx <= cur ? Math.max(0, cur - 1) : cur));
  };

  useEffect(() => {
    if (mode !== "smart" || smartStage !== "capture") return;
    const onPaste = (e: ClipboardEvent) => {
      const items = e.clipboardData && e.clipboardData.items;
      if (!items) return;
      const pics = Array.from(items)
        .filter((it) => it.type && it.type.indexOf("image") === 0)
        .map((it) => it.getAsFile())
        .filter((f): f is File => !!f);
      if (pics.length) addFiles(pics);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, smartStage]);

  // Free object URLs on unmount.
  useEffect(() => () => shots.forEach((s) => URL.revokeObjectURL(s.url)), []); // eslint-disable-line react-hooks/exhaustive-deps

  // Turn one extracted reservation object into a ready-to-edit draft.
  function draftFromObj(obj: Record<string, unknown>): Draft {
    const f: Form = { ...BV_BLANK };
    const ai: Record<string, boolean> = {};
    Object.keys(BV_BLANK).forEach((k) => {
      const v = obj ? obj[k] : null;
      if (v !== null && v !== undefined && String(v).trim() !== "") {
        f[k] = String(v);
        ai[k] = true;
      }
    });
    // Coerce extracted date/time into the formats the native pickers require.
    f.date = normDate(f.date);
    f.time = normTime(f.time);
    if (!f.lang) f.lang = "EN";
    if (!f.fare) {
      const s = bvSuggestFare(f.pickup, f.dropoff);
      if (s) f.fare = String(s);
    }
    return { form: f, aiFields: ai, createdId: null, createErr: null };
  }

  async function runExtract(useSample: boolean) {
    setSmartStage("scanning");
    setSmartErr(null);
    setNoRead(false);
    let objs: Record<string, unknown>[] = [];
    if (useSample) {
      await new Promise((r) => setTimeout(r, 1200));
      objs = [BV_SAMPLE_EXTRACTION];
      setSmartDemo(false);
    } else {
      try {
        const res = await extractReservations(shots.map((s) => s.file));
        objs = res.reservations || [];
        setSmartDemo(res.simulated);
      } catch (e) {
        // Hard failure (bad format / too large / service down): stay on the
        // capture screen and tell the driver exactly why, instead of a blank form.
        const code = e instanceof SmartError ? e.code : "service";
        const key = `err_${code}`;
        setSmartErr(t[key] ? key : "err_service");
        setSmartStage("capture");
        return;
      }
    }
    const usable = objs.filter((o) => hasAnyField(o));
    // Read OK but nothing usable → one blank draft + a clear notice.
    setDrafts(usable.length ? usable.map(draftFromObj) : [blankDraft()]);
    setActiveIdx(0);
    if (!usable.length) setNoRead(true);
    setAiRan(true);
    setSmartStage("form");
  }

  const missing = BV_REQUIRED.filter((k) => !String(form[k] || "").trim());
  const canCreate = missing.length === 0 && active.createdId == null;
  const single = drafts.length === 1;
  const createdDrafts = drafts.filter((d) => d.createdId != null);
  const readyCount = drafts.filter(
    (d) => d.createdId == null && BV_REQUIRED.every((k) => String(d.form[k] || "").trim()),
  ).length;
  const showDone = single ? active.createdId != null : createdDrafts.length === drafts.length;

  if (showDone && !single) {
    return (
      <MultiDone
        drafts={createdDrafts}
        t={t}
        onReset={reset}
        onView={() => router.push("/dashboard/rides")}
      />
    );
  }

  if (showDone) {
    return (
      <div style={{ padding: 28, maxWidth: 620, margin: "0 auto", display: "flex", flexDirection: "column", gap: 18 }}>
        <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: "32px 32px 28px", textAlign: "center", boxShadow: "var(--shadow-volt)" }}>
          <div style={{ display: "inline-flex", width: 56, height: 56, borderRadius: "50%", background: "var(--volt-bg)", border: "1px solid var(--volt-border)", alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
            <Icon name="circle-check" size={28} color="var(--volt)" />
          </div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 23, color: "var(--arctic)", marginBottom: 6 }}>{t.doneTitle}</div>
          <p style={{ fontSize: 14, color: "var(--silver)", margin: "0 auto 20px" }}>{t.doneSub}</p>
          <div style={{ background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: 16, textAlign: "left" }}>
            <RidePreviewBody form={form} />
          </div>
        </div>

        <ConfirmationCard form={form} t={t} />

        <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
          <Button variant="ghost" icon="plus" onClick={reset}>{t.addAnother}</Button>
          <Button variant="plain" icon="navigation" onClick={() => router.push("/dashboard/rides")}>{t.viewRides}</Button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: 28 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, gap: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 4, background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-full)", padding: 4 }}>
          {(
            [
              ["manual", t.manual, "pencil"],
              ["smart", t.smart, "sparkles"],
            ] as const
          ).map(([v, l, ic]) => (
            <button
              key={v}
              onClick={() => setMode(v as "manual" | "smart")}
              style={{
                padding: "9px 20px",
                borderRadius: "var(--radius-full)",
                cursor: "pointer",
                fontSize: 14,
                fontWeight: 600,
                border: "none",
                fontFamily: "var(--font-sans)",
                display: "flex",
                alignItems: "center",
                gap: 8,
                transition: "all .14s",
                background: mode === v ? "var(--volt-bg-20)" : "transparent",
                color: mode === v ? "var(--volt)" : "var(--silver)",
                boxShadow: mode === v ? "inset 0 0 0 1px var(--volt-border)" : "none",
              }}
            >
              <Icon name={ic} size={16} color="currentColor" />
              {l}
              {v === "smart" && (
                <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", background: "var(--volt)", color: "var(--void)", borderRadius: 4, padding: "1px 5px" }}>
                  {t.smartTag}
                </span>
              )}
            </button>
          ))}
        </div>
        <span style={{ fontSize: 13, color: "var(--fg3)", display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name={mode === "smart" ? "wand" : "pencil"} size={15} color="var(--fg3)" />
          {mode === "smart" ? t.modeSmartSub : t.modeManualSub}
        </span>
      </div>

      {mode === "smart" && smartStage !== "form" ? (
        <div style={{ maxWidth: 760, margin: "0 auto" }}>
          {smartErr && smartStage === "capture" && (
            <div style={{ display: "flex", alignItems: "center", gap: 9, background: "rgba(255,99,99,0.08)", border: "1px solid rgba(255,99,99,0.4)", borderRadius: "var(--radius-md)", padding: "12px 14px", marginBottom: 12 }}>
              <Icon name="alert-circle" size={16} color="var(--danger)" />
              <span style={{ fontSize: 13, color: "var(--silver)" }}>{t[smartErr] || t.err_service}</span>
            </div>
          )}
          <SmartCapture
            t={t}
            shots={shots}
            drag={drag}
            setDrag={setDrag}
            fileRef={fileRef}
            scanning={smartStage === "scanning"}
            onFiles={addFiles}
            onRemove={removeShot}
            onExtract={() => runExtract(false)}
            onStartOver={() => {
              clearShots();
              setSmartErr(null);
            }}
            onSample={() => {
              clearShots();
              runExtract(true);
            }}
          />
        </div>
      ) : (
        <>
          {!single && (
            <QueueStrip
              drafts={drafts}
              activeIdx={activeIdx}
              onPick={setActiveIdx}
              onDiscard={discardDraft}
              t={t}
            />
          )}
          <div className="bv-dash-grid" style={{ display: "grid", gridTemplateColumns: "1.65fr 1fr", gap: 22, alignItems: "start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {mode === "smart" && aiRan && <ReviewBanner t={t} missing={missing} form={form} demo={smartDemo} noRead={noRead} onBack={reset} />}

            <FormSection title={t.secClient} icon="user">
              <ClientNameField
                value={form.name}
                state={fieldState("name", form, aiFields, mode, aiRan)}
                t={t}
                onName={(v) => setForm((f) => ({ ...f, name: v, client_id: "" }))}
                onPick={(c) => {
                  setForm((f) => ({
                    ...f,
                    name: c.name,
                    phone: c.phone || f.phone,
                    lang: (c.lang || f.lang || "EN").toUpperCase() === "ES" ? "ES" : "EN",
                    client_id: String(c.id),
                  }));
                  // Prefill the route from what we know about this client (saved
                  // home + ride history), without overwriting anything typed.
                  getClientDetail(c.id)
                    .then((d) => {
                      const { home, airport } = inferRoute(d);
                      setForm((f) => ({
                        ...f,
                        pickup: f.pickup.trim() ? f.pickup : home,
                        dropoff: f.dropoff.trim() ? f.dropoff : airport,
                      }));
                    })
                    .catch(() => {});
                }}
              />
              <RideField id="phone" label={t.phone} icon="phone" ph={t.phonePh} value={form.phone} onChange={(v) => set("phone", v)} state={fieldState("phone", form, aiFields, mode, aiRan)} t={t} />
              <LangSeg label={t.prefLang} value={form.lang} onChange={(v) => set("lang", v)} t={t} />
            </FormSection>

            <FormSection title={t.secTrip} icon="navigation">
              <AutocompleteField id="pickup" label={t.pickup} icon="circle-dot" ph={t.pickupPh} value={form.pickup} onChange={(v) => set("pickup", v)} state={fieldState("pickup", form, aiFields, mode, aiRan)} t={t} />
              <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "center", margin: "-6px 0" }}>
                <button
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, pickup: f.dropoff, dropoff: f.pickup }))}
                  aria-label={t.swap}
                  title={t.swap}
                  style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 12px", borderRadius: "var(--radius-full)", background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", color: "var(--silver)", cursor: "pointer", fontSize: 12, fontWeight: 600, fontFamily: "var(--font-sans)" }}
                >
                  <Icon name="arrow-up-down" size={14} color="var(--volt)" />
                  {t.swap}
                </button>
              </div>
              <AutocompleteField id="dropoff" label={t.dropoff} icon="map-pin" ph={t.dropoffPh} value={form.dropoff} onChange={(v) => set("dropoff", v)} state={fieldState("dropoff", form, aiFields, mode, aiRan)} t={t} />
              <BVDatePicker label={t.date} value={form.date} onChange={(v) => set("date", v)} lang={lang} state={fieldState("date", form, aiFields, mode, aiRan)} half required />
              <BVTimePicker label={t.time} value={form.time} onChange={(v) => set("time", v)} lang={lang} state={fieldState("time", form, aiFields, mode, aiRan)} half required />
            </FormSection>

            <FormSection title={t.secExtra} icon="plane">
              <RideField id="flight" label={t.flight} icon="plane" ph={t.flightPh} value={form.flight} onChange={(v) => set("flight", v)} state={fieldState("flight", form, aiFields, mode, aiRan)} t={t} half />
              <RideField id="passengers" label={t.passengers} icon="users" ph={t.paxPh} value={form.passengers} onChange={(v) => set("passengers", v)} state={fieldState("passengers", form, aiFields, mode, aiRan)} t={t} half />
              <RideField
                id="fare"
                label={t.fare}
                icon="dollar-sign"
                ph="74"
                prefix="$"
                value={form.fare}
                onChange={(v) => set("fare", v.replace(/[^0-9.]/g, ""))}
                state={fieldState("fare", form, aiFields, mode, aiRan)}
                t={t}
                hint={!form.fare && fareHint ? (suggested ? t.suggestedQuote : t.suggested) : null}
                hintValue={fareHint}
                onHint={() => fareHint && set("fare", String(fareHint))}
              />
              <RideField id="notes" label={t.notes} icon="message-circle" ph={t.notesPh} value={form.notes} onChange={(v) => set("notes", v)} state={fieldState("notes", form, aiFields, mode, aiRan)} t={t} textarea />
            </FormSection>
          </div>

          <div style={{ position: "sticky", top: 88, display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: 20, boxShadow: "var(--shadow-card)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <Icon name="navigation" size={16} color="var(--volt)" />
                <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>{t.previewTitle}</span>
              </div>
              {form.name || form.pickup || form.dropoff ? (
                <RidePreviewBody form={form} />
              ) : (
                <p style={{ fontSize: 13, color: "var(--fg3)", lineHeight: 1.55, margin: 0 }}>{t.previewEmpty}</p>
              )}
              <div style={{ height: 1, background: "var(--line)", margin: "18px 0" }} />
              {single ? (
                <Button variant="solid" full icon="check" disabled={!canCreate || submitting} onClick={() => canCreate && submit()}>
                  {submitting ? t.creating : t.create}
                </Button>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <Button
                    variant="solid"
                    full
                    icon="check"
                    disabled={!canCreate || submitting}
                    onClick={() => canCreate && submit()}
                  >
                    {active.createdId != null ? t.createdTag : submitting ? t.creating : t.createThis}
                  </Button>
                  <Button
                    variant="plain"
                    full
                    icon="check"
                    disabled={readyCount === 0 || submitting}
                    onClick={createAllReady}
                  >
                    {t.createAll(readyCount)}
                  </Button>
                </div>
              )}
              {active.createErr && (
                <div style={{ fontSize: 12.5, color: "var(--danger)", marginTop: 10, display: "flex", alignItems: "flex-start", gap: 6 }}>
                  <Icon name="alert-circle" size={14} color="var(--danger)" />
                  <span>{active.createErr}</span>
                </div>
              )}
              {!canCreate ? (
                <div style={{ fontSize: 12, color: "var(--warning)", marginTop: 10, display: "flex", alignItems: "center", gap: 6, justifyContent: "center" }}>
                  <Icon name="alert-circle" size={13} color="var(--warning)" />
                  {t.needRequired}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 10, display: "flex", alignItems: "center", gap: 6, justifyContent: "center" }}>
                  <Icon name="credit-card" size={13} color="var(--fg3)" />
                  {t.squareNote}
                </div>
              )}
            </div>
          </div>
          </div>
        </>
      )}
    </div>
  );
}

function QueueStrip({
  drafts,
  activeIdx,
  onPick,
  onDiscard,
  t,
}: {
  drafts: { form: Form; createdId: number | null }[];
  activeIdx: number;
  onPick: (i: number) => void;
  onDiscard: (i: number) => void;
  t: any;
}) {
  return (
    <div style={{ marginBottom: 18, display: "flex", flexDirection: "column", gap: 9 }}>
      <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t.queueHint}</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {drafts.map((d, i) => {
          const miss = BV_REQUIRED.filter((k) => !String(d.form[k] || "").trim()).length;
          const done = d.createdId != null;
          const isActive = i === activeIdx;
          const label = String(d.form.name || "").trim() || t.reservationN(i + 1);
          return (
            <div
              key={i}
              onClick={() => onPick(i)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "7px 10px 7px 12px",
                borderRadius: "var(--radius-full)",
                border: `1px solid ${isActive ? "var(--volt-border)" : "var(--line-strong)"}`,
                background: isActive ? "var(--volt-bg-20)" : "var(--obsidian)",
                cursor: "pointer",
              }}
            >
              <Icon
                name={done ? "circle-check" : miss ? "alert-circle" : "user"}
                size={13}
                color={done ? "var(--volt)" : miss ? "var(--warning)" : "var(--silver)"}
              />
              <span
                style={{
                  fontSize: 12.5,
                  fontWeight: 600,
                  color: isActive ? "var(--volt)" : "var(--silver)",
                  maxWidth: 140,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {label}
              </span>
              <span
                style={{
                  fontSize: 11,
                  color: done ? "var(--volt)" : miss ? "var(--warning)" : "var(--fg3)",
                }}
              >
                {done ? t.createdTag : miss ? t.missingTag(miss) : t.readyTag}
              </span>
              {!done && drafts.length > 1 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDiscard(i);
                  }}
                  title={t.discard}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--fg3)",
                    display: "flex",
                    padding: 0,
                    marginLeft: 2,
                  }}
                >
                  <Icon name="x" size={13} color="currentColor" />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MultiDone({
  drafts,
  t,
  onReset,
  onView,
}: {
  drafts: { form: Form }[];
  t: any;
  onReset: () => void;
  onView: () => void;
}) {
  return (
    <div style={{ padding: 28, maxWidth: 620, margin: "0 auto", display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: "32px 32px 28px", textAlign: "center", boxShadow: "var(--shadow-volt)" }}>
        <div style={{ display: "inline-flex", width: 56, height: 56, borderRadius: "50%", background: "var(--volt-bg)", border: "1px solid var(--volt-border)", alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
          <Icon name="circle-check" size={28} color="var(--volt)" />
        </div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 23, color: "var(--arctic)", marginBottom: 6 }}>{t.multiDoneTitle(drafts.length)}</div>
        <p style={{ fontSize: 14, color: "var(--silver)", margin: "0 auto 20px" }}>{t.multiDoneSub}</p>
      </div>
      {drafts.map((d, i) => (
        <ConfirmationCard key={i} form={d.form} t={t} />
      ))}
      <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
        <Button variant="ghost" icon="plus" onClick={onReset}>{t.addAnother}</Button>
        <Button variant="plain" icon="navigation" onClick={onView}>{t.viewRides}</Button>
      </div>
    </div>
  );
}

function ReviewBanner({ t, missing, form, demo, noRead, onBack }: { t: any; missing: string[]; form: Form; demo?: boolean; noRead?: boolean; onBack: () => void }) {
  const tracked = ["name", "phone", "pickup", "dropoff", "date", "time", "flight", "passengers", "fare"];
  const found = tracked.filter((k) => String(form[k] || "").trim()).length;
  const total = tracked.length;
  const n = missing.length;
  return (
    <div
      style={{
        background: n ? "rgba(255,194,75,0.08)" : "var(--volt-bg)",
        border: `1px solid ${n ? "rgba(255,194,75,0.4)" : "var(--volt-border)"}`,
        borderRadius: "var(--radius-lg)",
        padding: "16px 18px",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 9,
            flexShrink: 0,
            background: n ? "rgba(255,194,75,0.14)" : "var(--volt-bg)",
            border: `1px solid ${n ? "rgba(255,194,75,0.4)" : "var(--volt-border)"}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Icon name="sparkles" size={17} color={n ? "var(--warning)" : "var(--volt)"} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>
            {t.foundOf(found, total)}{" "}
            {n ? <span style={{ color: "var(--warning)" }}>{t.confirm(n)}</span> : <span style={{ color: "var(--volt)" }}>{t.allGood}</span>}
          </div>
          {demo && (
            <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 6, display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="alert-circle" size={12} color="var(--fg3)" />
              {t.demoNote}
            </div>
          )}
          {noRead && (
            <div style={{ fontSize: 12, color: "var(--warning)", marginTop: 6, display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="alert-circle" size={12} color="var(--warning)" />
              {t.noReadNote}
            </div>
          )}
          {n > 0 && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
              {missing.map((k) => (
                <button
                  key={k}
                  onClick={() => {
                    const el = document.getElementById(k);
                    if (el) el.focus();
                  }}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    fontFamily: "var(--font-sans)",
                    cursor: "pointer",
                    background: "rgba(255,194,75,0.12)",
                    color: "var(--warning)",
                    border: "1px solid rgba(255,194,75,0.4)",
                    borderRadius: "var(--radius-full)",
                    padding: "5px 12px",
                  }}
                >
                  <Icon name="alert-circle" size={12} color="var(--warning)" />
                  {t[k] || k}
                </button>
              ))}
            </div>
          )}
        </div>
        <button onClick={onBack} title={t.backCapture} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--fg3)", display: "flex", padding: 2 }}>
          <Icon name="x" size={18} color="currentColor" />
        </button>
      </div>
    </div>
  );
}

function SmartCapture({
  t,
  shots,
  drag,
  setDrag,
  fileRef,
  scanning,
  onFiles,
  onRemove,
  onExtract,
  onStartOver,
  onSample,
}: {
  t: any;
  shots: Shot[];
  drag: boolean;
  setDrag: (v: boolean) => void;
  fileRef: React.RefObject<HTMLInputElement>;
  scanning: boolean;
  onFiles: (files: FileList | File[]) => void;
  onRemove: (i: number) => void;
  onExtract: () => void;
  onStartOver: () => void;
  onSample: () => void;
}) {
  const full = shots.length >= SMART_MAX_IMAGES;
  const pick = () => fileRef.current && fileRef.current.click();
  const hidden = (
    <input
      ref={fileRef}
      type="file"
      accept="image/*"
      multiple
      style={{ display: "none" }}
      onChange={(e) => {
        if (e.target.files && e.target.files.length) onFiles(e.target.files);
        e.target.value = "";
      }}
    />
  );

  if (scanning) {
    return (
      <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: 0, overflow: "hidden", maxWidth: 760, margin: "8px auto" }}>
        <div style={{ position: "relative", height: 280, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, background: "var(--obsidian-3)" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {shots[0] && <img src={shots[0].url} alt="" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: 0.18 }} />}
          <div style={{ position: "absolute", left: 0, right: 0, height: 2, background: "linear-gradient(90deg, transparent, var(--volt), transparent)", boxShadow: "var(--shadow-volt)", animation: "bv-scan 1.6s ease-in-out infinite alternate", top: 0 }} />
          <div style={{ position: "relative", width: 52, height: 52, borderRadius: "50%", border: "2px solid var(--volt-border)", borderTopColor: "var(--volt)", animation: "bv-spin 0.9s linear infinite" }} />
          <div style={{ position: "relative", textAlign: "center" }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 17, color: "var(--arctic)" }}>
              {shots.length ? t.scanningN(shots.length) : t.scanning}
            </div>
            <div style={{ fontSize: 13, color: "var(--silver)", marginTop: 5 }}>{t.scanningSub}</div>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div style={{ maxWidth: 760, margin: "8px auto" }}>
      {shots.length ? (
        <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <span style={{ fontSize: 13, color: "var(--silver)", fontFamily: "var(--font-sans)" }}>{t.shotsCount(shots.length)}</span>
            <span style={{ fontSize: 12, color: "var(--fg3)" }}>{t.maxImgs(SMART_MAX_IMAGES)}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 10 }}>
            {shots.map((s, i) => (
              <div key={s.url} style={{ position: "relative", borderRadius: "var(--radius-md)", overflow: "hidden", border: "1px solid var(--line)", background: "var(--void)", aspectRatio: "3 / 4" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={s.url} alt={`screenshot ${i + 1}`} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
                <button
                  onClick={() => onRemove(i)}
                  title={t.removeImg}
                  style={{ position: "absolute", top: 6, right: 6, width: 26, height: 26, borderRadius: "50%", border: "none", cursor: "pointer", background: "rgba(10,10,15,0.78)", color: "var(--arctic)", display: "flex", alignItems: "center", justifyContent: "center" }}
                >
                  <Icon name="x" size={14} color="currentColor" />
                </button>
              </div>
            ))}
            {!full && (
              <button
                onClick={pick}
                style={{ borderRadius: "var(--radius-md)", border: "1.5px dashed var(--line-strong)", background: "var(--obsidian-3)", color: "var(--silver)", cursor: "pointer", aspectRatio: "3 / 4", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, fontSize: 12, fontFamily: "var(--font-sans)" }}
              >
                <Icon name="plus" size={20} color="var(--volt)" />
                {t.addMore}
              </button>
            )}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 16, justifyContent: "space-between", alignItems: "center" }}>
            <Button variant="ghost" icon="x" onClick={onStartOver}>{t.startOver}</Button>
            <Button variant="solid" icon="sparkles" onClick={onExtract}>{t.extract}</Button>
          </div>
          {hidden}
        </div>
      ) : (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            if (e.dataTransfer.files && e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
          }}
          style={{
            border: `2px dashed ${drag ? "var(--volt)" : "var(--line-strong)"}`,
            borderRadius: "var(--radius-lg)",
            background: drag ? "var(--volt-bg)" : "var(--obsidian)",
            padding: "56px 32px",
            textAlign: "center",
            transition: "all .15s",
          }}
        >
          <div style={{ display: "inline-flex", width: 64, height: 64, borderRadius: 16, background: "var(--volt-bg)", border: "1px solid var(--volt-border)", alignItems: "center", justifyContent: "center", marginBottom: 18 }}>
            <Icon name="image" size={28} color="var(--volt)" />
          </div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 21, color: "var(--arctic)", marginBottom: 8 }}>{t.dropTitle}</div>
          <p style={{ fontSize: 14, color: "var(--silver)", maxWidth: 440, margin: "0 auto 22px", lineHeight: 1.5 }}>{t.dropSub}</p>
          <div style={{ display: "flex", gap: 10, justifyContent: "center", alignItems: "center", flexWrap: "wrap" }}>
            <Button variant="solid" icon="upload" onClick={pick}>{t.dropBtn}</Button>
            <Button variant="ghost" icon="sparkles" onClick={onSample}>{t.sample}</Button>
          </div>
          <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 16, display: "flex", alignItems: "center", gap: 6, justifyContent: "center" }}>
            <Icon name="clipboard" size={13} color="var(--fg3)" />
            {t.paste} · {t.maxImgs(SMART_MAX_IMAGES)}
          </div>
          {hidden}
        </div>
      )}
    </div>
  );
}

function FormSection({ title, icon, children }: { title: string; icon: string; children: ReactNode }) {
  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 16 }}>
        <Icon name={icon} size={16} color="var(--volt)" />
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 13, color: "var(--silver)", textTransform: "uppercase", letterSpacing: "0.12em" }}>{title}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>{children}</div>
    </div>
  );
}

function RideField({
  id,
  label,
  icon,
  ph,
  value,
  onChange,
  state = "normal",
  half,
  textarea,
  prefix,
  type,
  hint,
  hintValue,
  onHint,
  onKeyDown,
  t,
}: {
  id: string;
  label: string;
  icon?: string;
  ph?: string;
  value: string;
  onChange: (v: string) => void;
  state?: string;
  half?: boolean;
  textarea?: boolean;
  prefix?: string;
  type?: string;
  hint?: string | null;
  hintValue?: number | null;
  onHint?: () => void;
  onKeyDown?: (e: React.KeyboardEvent) => void;
  t: any;
}) {
  const [focus, setFocus] = useState(false);
  const border = state === "missing" ? "rgba(255,194,75,0.7)" : state === "ai" ? "var(--volt-border)" : "var(--line-strong)";
  const focusBorder = state === "missing" ? "var(--warning)" : "var(--volt)";
  const ring = state === "missing" ? "rgba(255,194,75,0.18)" : "var(--volt-bg)";
  const inputStyle: CSSProperties = {
    flex: 1,
    background: "transparent",
    border: "none",
    outline: "none",
    color: "var(--arctic)",
    fontSize: 14,
    fontFamily: "var(--font-sans)",
  };
  return (
    <label style={{ display: "block", gridColumn: textarea ? "1 / -1" : half ? undefined : "1 / -1" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 7 }}>
        <span style={{ fontSize: 12, color: "var(--fg3)", fontFamily: "var(--font-sans)" }}>
          {label}
          {BV_REQUIRED.includes(id) && <span style={{ color: "var(--warning)", marginLeft: 4 }}>*</span>}
        </span>
        {state === "ai" && (
          <span
            style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--volt)", background: "var(--volt-bg)", border: "1px solid var(--volt-border)", borderRadius: 5, padding: "1px 6px" }}
            title={t.aiHint}
          >
            <Icon name="sparkles" size={10} color="var(--volt)" />
            {t.smartTag}
          </span>
        )}
        {state === "missing" && <span style={{ fontSize: 10, fontWeight: 600, color: "var(--warning)" }}>{t.missingHint}</span>}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: textarea ? "flex-start" : "center",
          gap: 10,
          background: "var(--obsidian-3)",
          borderRadius: "var(--radius-md)",
          padding: "11px 13px",
          border: `1px solid ${focus ? focusBorder : border}`,
          boxShadow: focus ? `0 0 0 3px ${ring}` : "none",
          transition: "all .15s ease-out",
        }}
      >
        {icon && <Icon name={icon} size={17} color={focus ? focusBorder : state === "missing" ? "var(--warning)" : "var(--silver)"} style={{ marginTop: textarea ? 2 : 0 }} />}
        {prefix && <span style={{ color: "var(--silver)", fontSize: 14, fontFamily: "var(--font-sans)" }}>{prefix}</span>}
        {textarea ? (
          <textarea id={id} value={value} placeholder={ph} rows={2} onChange={(e) => onChange(e.target.value)} onKeyDown={onKeyDown} onFocus={() => setFocus(true)} onBlur={() => setFocus(false)} style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }} />
        ) : (
          <input id={id} type={type || "text"} value={value} placeholder={ph} onChange={(e) => onChange(e.target.value)} onKeyDown={onKeyDown} onFocus={() => setFocus(true)} onBlur={() => setFocus(false)} style={{ ...inputStyle, colorScheme: "dark" }} />
        )}
      </div>
      {hint && (
        <button type="button" onClick={onHint} style={{ marginTop: 7, background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: 12, color: "var(--volt)", display: "inline-flex", alignItems: "center", gap: 5, fontFamily: "var(--font-sans)" }}>
          <Icon name="plus" size={12} color="var(--volt)" />
          {hint}{hintValue ? ` · $${hintValue}` : ""}
        </button>
      )}
    </label>
  );
}

// Pickup/Dropoff with Google Places autocomplete. Wraps RideField in a relative
// container and renders the shared dropdown; each instance owns its own suggest
// state so pickup and dropoff don't interfere.
function AutocompleteField(props: {
  id: string;
  label: string;
  icon: string;
  ph: string;
  value: string;
  onChange: (v: string) => void;
  state: string;
  t: any;
}) {
  const ctl = useAddressSuggest({ onPick: props.onChange });
  return (
    <div ref={ctl.containerRef} style={{ position: "relative", gridColumn: "1 / -1" }}>
      <RideField
        {...props}
        onChange={(v) => {
          props.onChange(v);
          ctl.handleType(v);
        }}
        onKeyDown={ctl.handleKeyDown}
      />
      <SuggestionDropdown ctl={ctl} />
    </div>
  );
}

// Client full-name with CRM autocomplete. Typing searches saved clients; picking
// one fills phone + language and links the ride (client_id). Editing the name by
// hand clears the link so a brand-new name becomes a new client on submit.
function ClientNameField(props: {
  value: string;
  state: string;
  t: any;
  onName: (v: string) => void;
  onPick: (c: ClientLite) => void;
}) {
  const ctl = useClientSuggest({ onPick: props.onPick });
  return (
    <div ref={ctl.containerRef} style={{ position: "relative", gridColumn: "1 / -1" }}>
      <RideField
        id="name"
        label={props.t.name}
        icon="user"
        ph={props.t.namePh}
        value={props.value}
        state={props.state}
        t={props.t}
        onChange={(v) => {
          props.onName(v);
          ctl.handleType(v);
        }}
        onKeyDown={ctl.handleKeyDown}
      />
      <ClientSuggestionDropdown ctl={ctl} />
    </div>
  );
}

function LangSeg({ label, value, onChange, t }: { label: string; value: string; onChange: (v: string) => void; t: any }) {
  return (
    <div style={{ gridColumn: "1 / -1" }}>
      <div style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7, fontFamily: "var(--font-sans)" }}>{label}</div>
      <div style={{ display: "flex", gap: 4, background: "var(--obsidian-3)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-md)", padding: 4, width: "fit-content" }}>
        {(
          [
            ["EN", t.langEN],
            ["ES", t.langES],
          ] as const
        ).map(([v, l]) => (
          <button
            key={v}
            onClick={() => onChange(v)}
            style={{
              padding: "7px 18px",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 600,
              border: "none",
              fontFamily: "var(--font-sans)",
              background: value === v ? "var(--volt-bg-20)" : "transparent",
              color: value === v ? "var(--volt)" : "var(--silver)",
            }}
          >
            {l}
          </button>
        ))}
      </div>
    </div>
  );
}

function ConfirmationCard({ form, t }: { form: Form; t: any }) {
  const msg = bvConfirmationMsg(form);
  const [choice, setChoice] = useState<null | "auto" | "manual">(null);
  const [copied, setCopied] = useState(false);
  const copy = () => {
    const done = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1900);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(msg).then(done, done);
    else done();
  };
  return (
    <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 22 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <Icon name="message-circle" size={17} color="var(--volt)" />
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15, color: "var(--arctic)" }}>{t.confTitle}</div>
            <div style={{ fontSize: 12, color: "var(--fg3)" }}>{t.confSub}</div>
          </div>
        </div>
        <Pill tone="muted" style={{ fontSize: 10, padding: "3px 10px" }}>{String(form.lang || "EN").toUpperCase()}</Pill>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: "var(--fg3)", marginBottom: 8 }}>
        <Icon name="user" size={13} color="var(--fg3)" />
        {t.to} {form.name || "—"} · {form.phone || "—"}
      </div>
      <div
        style={{
          background: "var(--obsidian-3)",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--radius-md)",
          borderTopLeftRadius: 4,
          padding: "14px 16px",
          whiteSpace: "pre-line",
          fontSize: 13.5,
          lineHeight: 1.6,
          color: "var(--silver)",
          fontFamily: "var(--font-sans)",
        }}
      >
        {msg}
      </div>

      <div style={{ height: 1, background: "var(--line)", margin: "18px 0" }} />

      {choice === null && (
        <div>
          <div style={{ fontSize: 13, color: "var(--silver)", marginBottom: 12, display: "flex", alignItems: "center", gap: 7 }}>
            <Icon name="send" size={14} color="var(--volt)" />
            {t.sendQ}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button variant="solid" icon="message-circle" onClick={() => setChoice("auto")}>{t.sendAuto}</Button>
            <Button variant="ghost" icon="clipboard" onClick={() => setChoice("manual")}>{t.sendManual}</Button>
          </div>
        </div>
      )}

      {choice === "auto" && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, background: "rgba(43,212,160,0.08)", border: "1px solid rgba(43,212,160,0.4)", borderRadius: "var(--radius-md)", padding: "14px 16px" }}>
          <div style={{ width: 34, height: 34, borderRadius: 9, flexShrink: 0, background: "rgba(43,212,160,0.14)", border: "1px solid rgba(43,212,160,0.4)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icon name="circle-check" size={17} color="var(--success)" />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 14, color: "var(--arctic)" }}>{t.sentAuto}</div>
            <div style={{ fontSize: 12, color: "var(--silver)" }}>{t.autoNote} {form.phone || "—"}</div>
          </div>
          <button onClick={() => setChoice(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--fg3)", fontSize: 12, fontFamily: "var(--font-sans)", textDecoration: "underline", whiteSpace: "nowrap" }}>{t.another}</button>
        </div>
      )}

      {choice === "manual" && (
        <div>
          <div style={{ fontSize: 13, color: "var(--silver)", marginBottom: 12, display: "flex", alignItems: "center", gap: 7 }}>
            <Icon name="clipboard" size={14} color="var(--volt)" />
            {t.manualHint}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <Button variant={copied ? "ghost" : "solid"} icon={copied ? "check" : "clipboard"} onClick={copy}>{copied ? t.copied : t.copy}</Button>
            <button onClick={() => setChoice(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--fg3)", fontSize: 12, fontFamily: "var(--font-sans)", textDecoration: "underline" }}>{t.another}</button>
          </div>
        </div>
      )}
    </div>
  );
}

function RidePreviewBody({ form }: { form: Form }) {
  const Row = ({ icon, children, strong }: { icon: string; children: ReactNode; strong?: boolean }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13, color: strong ? "var(--arctic)" : "var(--silver)", fontWeight: strong ? 600 : 400, fontFamily: "var(--font-sans)", minWidth: 0 }}>
      <Icon name={icon} size={14} color="var(--volt)" />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{children}</span>
    </div>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 17, color: "var(--arctic)" }}>{form.name || "—"}</div>
        {form.lang && <Pill tone="muted" style={{ fontSize: 10, padding: "3px 9px" }}>{form.lang}</Pill>}
      </div>
      {(form.pickup || form.dropoff) && (
        <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13, color: "var(--silver)", minWidth: 0 }}>
          <Icon name="circle-dot" size={14} color="var(--volt)" />
          <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{form.pickup || "—"}</span>
          <Icon name="arrow-right" size={13} color="var(--fg3)" />
          <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{form.dropoff || "—"}</span>
        </div>
      )}
      {(form.date || form.time) && <Row icon="calendar">{[form.date, form.time].filter(Boolean).join(" · ")}</Row>}
      {form.flight && <Row icon="plane">{form.flight}</Row>}
      {form.passengers && <Row icon="users">{form.passengers}</Row>}
      {form.notes && <Row icon="message-circle">{form.notes}</Row>}
      {form.fare && <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 26, color: "var(--volt)", marginTop: 4 }}>${form.fare}</div>}
    </div>
  );
}
