/* Black Volt Mobility — driver dashboard sample data (mock). */

export type RideUiStatus = "upcoming" | "active" | "done" | "cancelled" | "overdue";

export interface Ride {
  id: string;
  rid?: number; // backend ride id (for detail fetch)
  client: string;
  from: string;
  to: string;
  time: string;
  fare: number;
  status: RideUiStatus;
  overdue?: boolean; // pickup time passed, still active — needs confirmation
  flight: string | null;
}

export const BV_RIDES: Ride[] = [
  { id: "ENV-4827", client: "Alex Rivera", from: "Downtown Denver", to: "Denver Intl (DEN)", time: "Today · 14:20", fare: 74, status: "upcoming", flight: "UA 2293" },
  { id: "ENV-4826", client: "Priya Shah", from: "Cherry Creek", to: "Denver Intl (DEN)", time: "Today · 16:05", fare: 68, status: "upcoming", flight: "DL 1180" },
  { id: "ENV-4825", client: "Marcus Webb", from: "DEN", to: "The Ritz-Carlton", time: "Today · 09:40", fare: 82, status: "active", flight: "AA 514" },
  { id: "ENV-4824", client: "Sofia Lang", from: "Aurora", to: "Union Station", time: "Today · 08:10", fare: 39, status: "done", flight: null },
  { id: "ENV-4823", client: "James Okafor", from: "DEN", to: "Boulder", time: "Yesterday · 22:30", fare: 110, status: "done", flight: "WN 880" },
  { id: "ENV-4822", client: "Lena Costa", from: "Highlands", to: "DEN", time: "Yesterday · 17:55", fare: 71, status: "done", flight: "F9 412" },
];

export interface Client {
  name: string;
  phone: string;
  rides: number;
  spend: number;
  tier: "VIP" | "Regular" | "New";
  lang: string;
}

export const BV_CLIENTS: Client[] = [
  { name: "Alex Rivera", phone: "+1 303 555 0142", rides: 14, spend: 1080, tier: "VIP", lang: "EN" },
  { name: "Priya Shah", phone: "+1 720 555 0199", rides: 9, spend: 612, tier: "Regular", lang: "EN" },
  { name: "Marcus Webb", phone: "+1 303 555 0177", rides: 22, spend: 1840, tier: "VIP", lang: "EN" },
  { name: "Sofia Lang", phone: "+1 720 555 0123", rides: 3, spend: 188, tier: "New", lang: "ES" },
  { name: "James Okafor", phone: "+1 303 555 0188", rides: 7, spend: 540, tier: "Regular", lang: "EN" },
];

export interface CalRide {
  t: string;
  c: string;
  s: RideUiStatus;
  rid?: number;
}

export const CAL_RIDES: Record<number, CalRide[]> = {
  4: [{ t: "08:10", c: "S. Lang", s: "done" }],
  7: [
    { t: "14:20", c: "M. Webb", s: "done" },
    { t: "19:00", c: "A. Rivera", s: "done" },
  ],
  11: [{ t: "22:30", c: "J. Okafor", s: "done" }],
  14: [{ t: "09:40", c: "M. Webb", s: "done" }],
  18: [
    { t: "17:55", c: "L. Costa", s: "done" },
    { t: "21:10", c: "P. Shah", s: "done" },
  ],
  22: [{ t: "06:30", c: "A. Rivera", s: "done" }],
  24: [
    { t: "13:00", c: "S. Lang", s: "done" },
    { t: "15:30", c: "M. Webb", s: "done" },
    { t: "20:00", c: "P. Shah", s: "done" },
  ],
  27: [{ t: "11:00", c: "J. Okafor", s: "done" }],
  29: [
    { t: "09:40", c: "M. Webb", s: "active" },
    { t: "14:20", c: "A. Rivera", s: "upcoming" },
    { t: "16:05", c: "P. Shah", s: "upcoming" },
  ],
  30: [{ t: "10:00", c: "L. Costa", s: "upcoming" }],
  31: [{ t: "08:00", c: "S. Lang", s: "upcoming" }],
};

export const CAL_STATUS: Record<string, string> = {
  upcoming: "var(--volt)",
  active: "var(--warning)",
  done: "var(--success)",
  cancelled: "var(--danger)",
};

export interface ThreadMsg {
  from: "client" | "ai";
  text: string;
  ai?: boolean;
}
export interface Thread {
  id: number;
  client: string;
  channel: "sms" | "call" | "chat";
  time: string;
  unread: boolean;
  snippet: string;
  duration?: string;
  summary?: string;
  msgs: ThreadMsg[];
}

export const BV_THREADS: Thread[] = [
  {
    id: 1,
    client: "Alex Rivera",
    channel: "sms",
    time: "2m",
    unread: true,
    snippet: "Can you come 10 min earlier?",
    msgs: [
      { from: "client", text: "Hi! Can you come 10 min earlier? Meeting moved up." },
      { from: "ai", text: "Of course, Alex. I've moved your pickup to 14:10. Ender's EV9 will be out front.", ai: true },
      { from: "client", text: "Perfect, thank you 🙏" },
    ],
  },
  {
    id: 2,
    client: "Priya Shah",
    channel: "call",
    time: "18m",
    unread: true,
    snippet: "AI call · 1m 12s · rebooked flight pickup",
    duration: "1m 12s",
    summary: "Flight DL 1180 delayed 35 min. Pickup auto-moved 16:05 → 16:40. Client confirmed.",
    msgs: [
      { from: "ai", text: "Hi Priya, this is the Black Volt assistant. I see flight DL 1180 is delayed 35 minutes.", ai: true },
      { from: "client", text: "Oh good you caught that — yes please push my pickup back." },
      { from: "ai", text: "Done — pickup moved to 16:40 at DEN arrivals. Ender will track your flight.", ai: true },
    ],
  },
  {
    id: 3,
    client: "Marcus Webb",
    channel: "chat",
    time: "1h",
    unread: false,
    snippet: "Fare to Boulder tonight?",
    msgs: [
      { from: "client", text: "What's the fare to Boulder tonight around 11pm?" },
      { from: "ai", text: "DEN → Boulder is ~$110 metered; after 22:00 Fri/Sat a ×1.4 peak applies. Want me to book it?", ai: true },
    ],
  },
  {
    id: 4,
    client: "Sofia Lang",
    channel: "sms",
    time: "3h",
    unread: false,
    snippet: "¿Aceptan pago en efectivo?",
    msgs: [
      { from: "client", text: "Hola, ¿aceptan pago en efectivo?" },
      { from: "ai", text: "Hola Sofia — pagamos con Square (tarjeta) para tu seguridad. Te llega el recibo al instante.", ai: true },
    ],
  },
];

export const CHANNEL: Record<string, { icon: string; labelKey: string; color: string }> = {
  sms: { icon: "message-circle", labelKey: "dash.inbox.ch.sms", color: "var(--volt)" },
  call: { icon: "phone", labelKey: "dash.inbox.ch.call", color: "var(--success)" },
  chat: { icon: "sparkles", labelKey: "dash.inbox.ch.chat", color: "var(--warning)" },
};
