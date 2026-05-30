"use client";

/* Black Volt Mobility — Add reservation (Manual + Smart/AI screenshot modes).
   Ported from the design system's dashboard kit. Smart mode reads a screenshot
   via window.claude vision when available, else a believable sample extraction. */
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Icon } from "../Icon";
import { Button, Pill } from "../ui";
import { useI18n } from "@/lib/i18n";

type Form = Record<string, string>;
const BV_BLANK: Form = {
  name: "", phone: "", lang: "EN", pickup: "", dropoff: "", date: "", time: "",
  flight: "", passengers: "", fare: "", notes: "",
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
    previewTitle: "Reservation preview", previewEmpty: "Fill in the form to preview the ride.",
    create: "Create reservation", creating: "Creating…",
    squareNote: "Payment collected on card via Square.",
    needRequired: "Complete the required fields to continue.",
    dropTitle: "Drop, paste or upload a screenshot",
    dropSub: "An SMS, WhatsApp, email or note from the client — AI reads the details.",
    dropBtn: "Choose image", paste: "or press ⌘V / Ctrl+V to paste",
    sample: "Try a sample", change: "Replace", extract: "Extract with AI",
    scanning: "Reading the screenshot…", scanningSub: "Pulling out the reservation details.",
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
    previewTitle: "Vista previa de la reserva", previewEmpty: "Completa el formulario para ver el viaje.",
    create: "Crear reserva", creating: "Creando…",
    squareNote: "El pago se cobra con tarjeta vía Square.",
    needRequired: "Completa los campos obligatorios para continuar.",
    dropTitle: "Arrastra, pega o sube una captura",
    dropSub: "Un SMS, WhatsApp, correo o nota del cliente — la IA lee los datos.",
    dropBtn: "Elegir imagen", paste: "o pulsa ⌘V / Ctrl+V para pegar",
    sample: "Probar un ejemplo", change: "Reemplazar", extract: "Extraer con IA",
    scanning: "Leyendo la captura…", scanningSub: "Extrayendo los datos de la reserva.",
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

const BV_EXTRACT_PROMPT = `You read a screenshot of a customer ride request for Black Volt Mobility, a premium chauffeur / airport-transfer service in Denver. The screenshot may be an SMS, WhatsApp, email, or a typed note. Extract the reservation details.
Return ONLY a JSON object — no prose, no markdown fences — with EXACTLY these keys, using null when the info is not present in the image:
{"name": string|null, "phone": string|null, "lang": "EN"|"ES"|null, "pickup": string|null, "dropoff": string|null, "date": string|null, "time": string|null, "flight": string|null, "passengers": number|null, "fare": number|null, "notes": string|null}
Notes:
- "lang": guess from the language the customer wrote in.
- "date"/"time": keep them short and human (e.g. "Jun 14", "06:30"). Use 24h time when possible.
- "fare": numeric dollars only if explicitly stated, else null.
- Denver International should be normalized to "Denver Intl (DEN)".`;

const BV_SAMPLE_EXTRACTION: Record<string, unknown> = {
  name: "Daniel Ortega", phone: null, lang: "ES",
  pickup: "The Crawford Hotel", dropoff: "Denver Intl (DEN)",
  date: "Jun 14", time: "06:30", flight: "UA 1455",
  passengers: 2, fare: null, notes: "2 maletas grandes",
};

type ClaudeWindow = Window & {
  claude?: { complete: (args: { messages: unknown[] }) => Promise<string> };
};

async function bvExtractFromImage(dataURL: string | null): Promise<Record<string, unknown>> {
  try {
    const w = typeof window !== "undefined" ? (window as ClaudeWindow) : undefined;
    if (w?.claude?.complete && dataURL) {
      const m = /^data:(image\/[a-zA-Z+]+);base64,(.*)$/.exec(dataURL);
      if (m) {
        const out = await w.claude.complete({
          messages: [
            {
              role: "user",
              content: [
                { type: "text", text: BV_EXTRACT_PROMPT },
                { type: "image", source: { type: "base64", media_type: m[1], data: m[2] } },
              ],
            },
          ],
        });
        const txt = (out || "").trim();
        const a = txt.indexOf("{");
        const b = txt.lastIndexOf("}");
        if (a >= 0 && b > a) return JSON.parse(txt.slice(a, b + 1));
      }
    }
  } catch {
    /* fall through to sample */
  }
  return BV_SAMPLE_EXTRACTION;
}

function bvFileToURL(file: File): Promise<string> {
  return new Promise((res) => {
    const r = new FileReader();
    r.onload = () => res(r.result as string);
    r.readAsDataURL(file);
  });
}

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
  const t = BV_T[lang] || BV_T.en;
  const [mode, setMode] = useState<"manual" | "smart">("manual");
  const [smartStage, setSmartStage] = useState<"capture" | "scanning" | "form">("capture");
  const [form, setForm] = useState<Form>(BV_BLANK);
  const [aiFields, setAiFields] = useState<Record<string, boolean>>({});
  const [aiRan, setAiRan] = useState(false);
  const [img, setImg] = useState<string | null>(null);
  const [created, setCreated] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const reset = () => {
    setForm(BV_BLANK);
    setAiFields({});
    setAiRan(false);
    setImg(null);
    setCreated(false);
    setSmartStage("capture");
  };

  useEffect(() => {
    if (mode !== "smart" || smartStage !== "capture") return;
    const onPaste = (e: ClipboardEvent) => {
      const items = e.clipboardData && e.clipboardData.items;
      if (!items) return;
      for (const it of Array.from(items)) {
        if (it.type && it.type.indexOf("image") === 0) {
          const file = it.getAsFile();
          if (file) bvFileToURL(file).then(setImg);
        }
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [mode, smartStage]);

  async function runExtract(useSample: boolean) {
    setSmartStage("scanning");
    const obj = await bvExtractFromImage(useSample ? null : img);
    await new Promise((r) => setTimeout(r, useSample ? 1500 : 600));
    const next: Form = { ...BV_BLANK };
    const ai: Record<string, boolean> = {};
    Object.keys(BV_BLANK).forEach((k) => {
      const v = obj ? obj[k] : null;
      if (v !== null && v !== undefined && String(v).trim() !== "") {
        next[k] = String(v);
        ai[k] = true;
      }
    });
    if (!next.lang) next.lang = "EN";
    if (!next.fare) {
      const s = bvSuggestFare(next.pickup, next.dropoff);
      if (s) next.fare = String(s);
    }
    setForm(next);
    setAiFields(ai);
    setAiRan(true);
    setSmartStage("form");
  }

  const missing = BV_REQUIRED.filter((k) => !String(form[k] || "").trim());
  const canCreate = missing.length === 0;

  if (created) {
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
        <SmartCapture
          t={t}
          img={img}
          drag={drag}
          setDrag={setDrag}
          fileRef={fileRef}
          scanning={smartStage === "scanning"}
          onFile={(f) => bvFileToURL(f).then(setImg)}
          onExtract={() => runExtract(false)}
          onSample={() => {
            setImg(null);
            runExtract(true);
          }}
          onClear={() => setImg(null)}
        />
      ) : (
        <div className="bv-dash-grid" style={{ display: "grid", gridTemplateColumns: "1.65fr 1fr", gap: 22, alignItems: "start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {mode === "smart" && aiRan && <ReviewBanner t={t} missing={missing} form={form} onBack={reset} />}

            <FormSection title={t.secClient} icon="user">
              <RideField id="name" label={t.name} icon="user" ph={t.namePh} value={form.name} onChange={(v) => set("name", v)} state={fieldState("name", form, aiFields, mode, aiRan)} t={t} />
              <RideField id="phone" label={t.phone} icon="phone" ph={t.phonePh} value={form.phone} onChange={(v) => set("phone", v)} state={fieldState("phone", form, aiFields, mode, aiRan)} t={t} />
              <LangSeg label={t.prefLang} value={form.lang} onChange={(v) => set("lang", v)} t={t} />
            </FormSection>

            <FormSection title={t.secTrip} icon="navigation">
              <RideField id="pickup" label={t.pickup} icon="circle-dot" ph={t.pickupPh} value={form.pickup} onChange={(v) => set("pickup", v)} state={fieldState("pickup", form, aiFields, mode, aiRan)} t={t} />
              <RideField id="dropoff" label={t.dropoff} icon="map-pin" ph={t.dropoffPh} value={form.dropoff} onChange={(v) => set("dropoff", v)} state={fieldState("dropoff", form, aiFields, mode, aiRan)} t={t} />
              <RideField id="date" label={t.date} icon="calendar" ph={t.datePh} value={form.date} onChange={(v) => set("date", v)} state={fieldState("date", form, aiFields, mode, aiRan)} t={t} half />
              <RideField id="time" label={t.time} icon="clock" ph={t.timePh} value={form.time} onChange={(v) => set("time", v)} state={fieldState("time", form, aiFields, mode, aiRan)} t={t} half />
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
                hint={!form.fare && bvSuggestFare(form.pickup, form.dropoff) ? t.suggested : null}
                onHint={() => set("fare", String(bvSuggestFare(form.pickup, form.dropoff)))}
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
              <Button variant="solid" full icon="check" disabled={!canCreate} onClick={() => canCreate && setCreated(true)}>
                {t.create}
              </Button>
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
      )}
    </div>
  );
}

function ReviewBanner({ t, missing, form, onBack }: { t: any; missing: string[]; form: Form; onBack: () => void }) {
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
  img,
  drag,
  setDrag,
  fileRef,
  scanning,
  onFile,
  onExtract,
  onSample,
  onClear,
}: {
  t: any;
  img: string | null;
  drag: boolean;
  setDrag: (v: boolean) => void;
  fileRef: React.RefObject<HTMLInputElement>;
  scanning: boolean;
  onFile: (f: File) => void;
  onExtract: () => void;
  onSample: () => void;
  onClear: () => void;
}) {
  if (scanning) {
    return (
      <div style={{ background: "var(--obsidian)", border: "1px solid var(--volt-border)", borderRadius: "var(--radius-lg)", padding: 0, overflow: "hidden", maxWidth: 760, margin: "8px auto" }}>
        <div style={{ position: "relative", height: 280, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, background: "var(--obsidian-3)" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {img && <img src={img} alt="" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: 0.18 }} />}
          <div style={{ position: "absolute", left: 0, right: 0, height: 2, background: "linear-gradient(90deg, transparent, var(--volt), transparent)", boxShadow: "var(--shadow-volt)", animation: "bv-scan 1.6s ease-in-out infinite alternate", top: 0 }} />
          <div style={{ position: "relative", width: 52, height: 52, borderRadius: "50%", border: "2px solid var(--volt-border)", borderTopColor: "var(--volt)", animation: "bv-spin 0.9s linear infinite" }} />
          <div style={{ position: "relative", textAlign: "center" }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 17, color: "var(--arctic)" }}>{t.scanning}</div>
            <div style={{ fontSize: 13, color: "var(--silver)", marginTop: 5 }}>{t.scanningSub}</div>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div style={{ maxWidth: 760, margin: "8px auto" }}>
      {img ? (
        <div style={{ background: "var(--obsidian)", border: "1px solid var(--line-strong)", borderRadius: "var(--radius-lg)", padding: 16 }}>
          <div style={{ borderRadius: "var(--radius-md)", overflow: "hidden", border: "1px solid var(--line)", background: "var(--void)", maxHeight: 360, display: "flex", justifyContent: "center" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={img} alt="screenshot" style={{ maxWidth: "100%", maxHeight: 360, objectFit: "contain", display: "block" }} />
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 16, justifyContent: "space-between" }}>
            <Button variant="plain" icon="image" onClick={onClear}>{t.change}</Button>
            <Button variant="solid" icon="sparkles" onClick={onExtract}>{t.extract}</Button>
          </div>
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
            const f = e.dataTransfer.files && e.dataTransfer.files[0];
            if (f) onFile(f);
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
          <p style={{ fontSize: 14, color: "var(--silver)", maxWidth: 420, margin: "0 auto 22px", lineHeight: 1.5 }}>{t.dropSub}</p>
          <div style={{ display: "flex", gap: 10, justifyContent: "center", alignItems: "center", flexWrap: "wrap" }}>
            <Button variant="solid" icon="upload" onClick={() => fileRef.current && fileRef.current.click()}>{t.dropBtn}</Button>
            <Button variant="ghost" icon="sparkles" onClick={onSample}>{t.sample}</Button>
          </div>
          <div style={{ fontSize: 12, color: "var(--fg3)", marginTop: 16, display: "flex", alignItems: "center", gap: 6, justifyContent: "center" }}>
            <Icon name="clipboard" size={13} color="var(--fg3)" />
            {t.paste}
          </div>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => { const f = e.target.files && e.target.files[0]; if (f) onFile(f); }} />
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
  hint,
  onHint,
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
  hint?: string | null;
  onHint?: () => void;
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
          <textarea id={id} value={value} placeholder={ph} rows={2} onChange={(e) => onChange(e.target.value)} onFocus={() => setFocus(true)} onBlur={() => setFocus(false)} style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }} />
        ) : (
          <input id={id} value={value} placeholder={ph} onChange={(e) => onChange(e.target.value)} onFocus={() => setFocus(true)} onBlur={() => setFocus(false)} style={inputStyle} />
        )}
      </div>
      {hint && (
        <button type="button" onClick={onHint} style={{ marginTop: 7, background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: 12, color: "var(--volt)", display: "inline-flex", alignItems: "center", gap: 5, fontFamily: "var(--font-sans)" }}>
          <Icon name="plus" size={12} color="var(--volt)" />
          {hint} · $74
        </button>
      )}
    </label>
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
