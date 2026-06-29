"use client";

import { useState } from "react";

const POINTS = "12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2";

function Star({ filled, size }: { filled: boolean; size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden
      fill={filled ? "var(--volt)" : "none"}
      stroke={filled ? "var(--volt)" : "var(--fg3)"}
      strokeWidth={1.6}
      style={{ display: "block" }}
    >
      <polygon points={POINTS} strokeLinejoin="round" />
    </svg>
  );
}

export default function StarRating({
  value,
  onChange,
  size = 22,
  readOnly = false,
}: {
  value: number;
  onChange?: (v: number) => void;
  size?: number;
  readOnly?: boolean;
}) {
  const [hover, setHover] = useState(0);
  const active = hover || value;
  const interactive = !readOnly && !!onChange;

  return (
    <div
      role={interactive ? "radiogroup" : "img"}
      aria-label={`Rating: ${value} of 5`}
      style={{ display: "inline-flex", gap: 3 }}
    >
      {[1, 2, 3, 4, 5].map((n) =>
        interactive ? (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            aria-label={`${n} star${n > 1 ? "s" : ""}`}
            onClick={() => onChange!(n)}
            onMouseEnter={() => setHover(n)}
            onMouseLeave={() => setHover(0)}
            style={{ background: "none", border: "none", padding: 0, cursor: "pointer", lineHeight: 0 }}
          >
            <Star filled={n <= active} size={size} />
          </button>
        ) : (
          <span key={n} style={{ lineHeight: 0 }}>
            <Star filled={n <= active} size={size} />
          </span>
        ),
      )}
    </div>
  );
}
