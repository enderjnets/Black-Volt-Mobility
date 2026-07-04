/* Black Volt Mobility — client AI helper. Uses window.claude.complete when
   present (Claude Design preview env); otherwise falls back to a smart mock so
   the prototype never breaks. Real wiring to Kimi/MiniMax happens server-side
   in Phase 7. */

/* Live pricing facts for the persona/mock. The owner tunes fares in the Rates
   dashboard, so nothing here hardcodes a dollar amount — Chat fetches the rate
   config and passes it in; without it the copy stays generic. */
export interface BvRates {
  denFlat?: number | null;
  base?: number | null;
  perMile?: number | null;
  minimum?: number | null;
}

function pricingFact(r?: BvRates | null): string {
  const den = r?.denFlat && r.denFlat > 0 ? `Denver Airport (DEN) is a flat $${Math.round(r.denFlat)}` : "Denver Airport (DEN) rides are a flat rate shown upfront at booking";
  const meter =
    r?.base && r?.perMile
      ? ` Other trips: about $${r.base} base + $${r.perMile}/mi${r.minimum ? `, $${Math.round(r.minimum)} minimum` : ""}.`
      : "";
  return `- Pricing is fixed and shown upfront, no surge except Fri/Sat 22:00–02:00 (×1.4). ${den}.${meter}`;
}

export const bvPersona = (rates?: BvRates | null) => `You are the Black Volt Mobility assistant — a premium all-electric chauffeur and airport-transfer service in Denver / Aurora, Colorado. The fleet is a single blacked-out Kia EV9 (7 seats, silent, all-electric). The owner-driver is Ender. Brand voice: premium, calm, concise — like a high-end black-car service, never hypey. Tagline: "Silent Power. Premium Arrival."

Facts you can use:
${pricingFact(rates)}
- You can help with: booking rides, fare estimates, changing pickup times, flight-tracking pickups, and general questions.
- Payment is by card via Square.

Rules:
- Reply in the SAME language as the customer (English or Spanish).
- Keep replies to 1–2 short sentences. Warm, premium, specific.
- Never invent features that don't exist. No emoji.
- Reply with ONLY the assistant's message text — no labels or quotes.`;

export interface BvMsg {
  role: "user" | "ai";
  text: string;
}

type ClaudeWindow = Window & {
  claude?: { complete: (args: { messages: { role: string; content: string }[] }) => Promise<string> };
};

export async function bvComplete(
  transcript: BvMsg[],
  opts?: { mock?: (q: string) => string; rates?: BvRates | null },
): Promise<string> {
  const last = [...transcript].reverse().find((m) => m.role === "user");
  const convo = transcript
    .map((m) => `${m.role === "user" ? "Customer" : "Assistant"}: ${m.text}`)
    .join("\n");
  try {
    const w = typeof window !== "undefined" ? (window as ClaudeWindow) : undefined;
    if (w?.claude?.complete) {
      const prompt = `${bvPersona(opts?.rates)}\n\nConversation so far:\n${convo}\n\nWrite the assistant's next reply to the customer.`;
      const out = await w.claude.complete({ messages: [{ role: "user", content: prompt }] });
      const text = (out || "").trim();
      if (text) return text;
    }
  } catch {
    /* fall through to mock */
  }
  return opts?.mock ? opts.mock(last ? last.text : "") : "Got it — Ender will take care of it.";
}
