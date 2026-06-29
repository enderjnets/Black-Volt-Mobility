import { Clock, Lock, PlaneTakeoff, ShieldCheck, Tag, UserCheck, Zap } from "lucide-react";

/**
 * Factual trust signals for the route landing pages. Every badge is a verifiable
 * statement about how Black Volt operates — NO invented reviews, ratings, or awards.
 *
 * The insurance badge is phrased conservatively. Only upgrade it to a specific
 * regulatory claim (e.g. "Licensed · CO PUC · $500k liability") once the owner
 * confirms the PUC permit and policy are active.
 */
const BADGES: { icon: typeof Zap; title: string; sub: string }[] = [
  { icon: UserCheck, title: "Owner-driven", sub: "Always the owner — never a random gig driver" },
  { icon: ShieldCheck, title: "Fully insured", sub: "Commercial luxury service, professionally insured" },
  { icon: Zap, title: "100% electric", sub: "Silent, zero-emission luxury SUV" },
  { icon: Tag, title: "Flat upfront price", sub: "Quoted before you book — no surge, ever" },
  { icon: PlaneTakeoff, title: "Flight-aware", sub: "We track your flight and adjust pickup time" },
  { icon: Lock, title: "Private & exclusive", sub: "Your ride only — never shared or pooled" },
];

export default function RouteTrust() {
  return (
    <section
      aria-label="Why book Black Volt"
      style={{
        marginTop: 28,
        padding: 18,
        background: "var(--obsidian-2)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius-lg)",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 14,
        }}
      >
        {BADGES.map(({ icon: Icon, title, sub }) => (
          <div key={title} style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
            <span
              style={{
                flex: "0 0 auto",
                width: 34,
                height: 34,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: "var(--radius-md)",
                background: "var(--volt-bg)",
                border: "1px solid var(--volt-border)",
              }}
            >
              <Icon size={18} color="var(--volt)" strokeWidth={2} aria-hidden />
            </span>
            <span style={{ display: "grid", gap: 2 }}>
              <span style={{ fontSize: 13.5, fontWeight: 700, color: "var(--arctic)" }}>{title}</span>
              <span style={{ fontSize: 12.5, lineHeight: 1.4, color: "var(--fg3)" }}>{sub}</span>
            </span>
          </div>
        ))}
      </div>
      <p
        style={{
          margin: "14px 0 0",
          paddingTop: 12,
          borderTop: "1px solid var(--line)",
          fontSize: 12,
          color: "var(--fg3)",
          display: "flex",
          alignItems: "center",
          gap: 7,
        }}
      >
        <Clock size={13} color="var(--fg3)" aria-hidden />
        Door-to-door across the Denver metro, DEN airport, and the Colorado mountains.
      </p>
    </section>
  );
}
