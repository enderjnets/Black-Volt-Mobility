"use client";

import { type CSSProperties, type ReactNode, useState } from "react";

import { Icon } from "./Icon";

/* ---- Logo ---- */
export function Logo({ size = 22, word = true }: { size?: number; word?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <Icon name="zap" size={size} color="#00E5FF" fill="#00E5FF" />
      {word && (
        <span
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: size * 0.82,
            letterSpacing: "0.04em",
            color: "var(--arctic)",
            textTransform: "uppercase",
            whiteSpace: "nowrap",
          }}
        >
          Black Volt <span style={{ color: "var(--volt)" }}>Mobility</span>
        </span>
      )}
    </div>
  );
}

type ButtonVariant = "solid" | "tint" | "ghost" | "plain";
export function Button({
  children,
  variant = "solid",
  icon,
  iconRight,
  onClick,
  disabled,
  full,
  size = "md",
  style,
}: {
  children?: ReactNode;
  variant?: ButtonVariant;
  icon?: string;
  iconRight?: string;
  onClick?: () => void;
  disabled?: boolean;
  full?: boolean;
  size?: "sm" | "md" | "lg";
  style?: CSSProperties;
}) {
  const [hover, setHover] = useState(false);
  const [press, setPress] = useState(false);
  const pad = size === "lg" ? "14px 26px" : size === "sm" ? "8px 16px" : "11px 22px";
  const fs = size === "lg" ? 16 : size === "sm" ? 13 : 14;
  const base: CSSProperties = {
    fontFamily: "var(--font-sans)",
    fontWeight: 600,
    fontSize: fs,
    borderRadius: "var(--radius-md)",
    padding: pad,
    border: "none",
    cursor: disabled ? "not-allowed" : "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    width: full ? "100%" : "auto",
    transition: "all .16s ease-out",
    transform: press && !disabled ? "scale(0.975)" : "none",
    whiteSpace: "nowrap",
    ...style,
  };
  const variants: Record<ButtonVariant, CSSProperties> = {
    solid: {
      background: disabled ? "rgba(0,229,255,0.2)" : hover ? "var(--volt-dim)" : "var(--volt)",
      color: "var(--void)",
      boxShadow: disabled ? "none" : "var(--shadow-volt-sm)",
      opacity: disabled ? 0.5 : 1,
    },
    tint: {
      background: hover ? "rgba(0,229,255,0.28)" : "var(--volt-bg-20)",
      color: "var(--volt)",
      opacity: disabled ? 0.5 : 1,
    },
    ghost: {
      background: hover ? "rgba(0,229,255,0.10)" : "transparent",
      color: hover ? "var(--arctic)" : "var(--silver)",
      border: "1px solid var(--volt-border)",
    },
    plain: {
      background: hover ? "var(--obsidian-2)" : "transparent",
      color: hover ? "var(--arctic)" : "var(--silver)",
    },
  };
  return (
    <button
      style={{ ...base, ...variants[variant] }}
      onClick={disabled ? undefined : onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => {
        setHover(false);
        setPress(false);
      }}
      onMouseDown={() => setPress(true)}
      onMouseUp={() => setPress(false)}
    >
      {icon && (
        <Icon
          name={icon}
          size={fs + 4}
          color="currentColor"
          fill={variant === "solid" && icon === "zap" ? "currentColor" : "none"}
        />
      )}
      {children}
      {iconRight && <Icon name={iconRight} size={fs + 2} color="currentColor" />}
    </button>
  );
}

type PillTone = "volt" | "success" | "warning" | "muted";
export function Pill({
  children,
  icon,
  tone = "volt",
  style,
}: {
  children?: ReactNode;
  icon?: string;
  tone?: PillTone;
  style?: CSSProperties;
}) {
  const tones: Record<PillTone, { border: string; color: string }> = {
    volt: { border: "var(--volt-border)", color: "var(--volt)" },
    success: { border: "rgba(43,212,160,0.4)", color: "var(--success)" },
    warning: { border: "rgba(255,194,75,0.4)", color: "var(--warning)" },
    muted: { border: "var(--line-strong)", color: "var(--silver)" },
  };
  const tn = tones[tone];
  return (
    <span
      style={{
        fontFamily: "var(--font-display)",
        fontWeight: 600,
        fontSize: 12,
        textTransform: "uppercase",
        letterSpacing: "0.18em",
        borderRadius: "var(--radius-full)",
        border: `1px solid ${tn.border}`,
        color: tn.color,
        padding: "5px 14px",
        display: "inline-flex",
        alignItems: "center",
        gap: 7,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {icon && (
        <Icon name={icon} size={13} color="currentColor" fill={icon === "zap" ? "currentColor" : "none"} />
      )}
      {children}
    </span>
  );
}

export function Field({
  icon,
  label,
  value,
  placeholder,
  onChange,
  type = "text",
  readOnly,
}: {
  icon?: string;
  label?: string;
  value?: string;
  placeholder?: string;
  onChange?: (v: string) => void;
  type?: string;
  readOnly?: boolean;
}) {
  const [focus, setFocus] = useState(false);
  return (
    <label style={{ display: "block" }}>
      {label && (
        <div
          style={{ fontSize: 12, color: "var(--fg3)", marginBottom: 7, fontFamily: "var(--font-sans)" }}
        >
          {label}
        </div>
      )}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: "var(--obsidian-3)",
          borderRadius: "var(--radius-md)",
          padding: "12px 14px",
          border: `1px solid ${focus ? "var(--volt)" : "var(--line-strong)"}`,
          boxShadow: focus ? "0 0 0 3px var(--volt-bg)" : "none",
          transition: "all .15s ease-out",
        }}
      >
        {icon && <Icon name={icon} size={18} color={focus ? "var(--volt)" : "var(--silver)"} />}
        <input
          type={type}
          value={value}
          placeholder={placeholder}
          readOnly={readOnly}
          onChange={(e) => onChange && onChange(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => setFocus(false)}
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            color: "var(--arctic)",
            fontSize: 14,
            fontFamily: "var(--font-sans)",
          }}
        />
      </div>
    </label>
  );
}

export function Card({
  children,
  glow,
  pad = 20,
  style,
}: {
  children?: ReactNode;
  glow?: boolean;
  pad?: number;
  style?: CSSProperties;
}) {
  return (
    <div
      style={{
        background: "var(--obsidian)",
        border: "1px solid var(--volt-border)",
        borderRadius: "var(--radius-lg)",
        padding: pad,
        boxShadow: glow ? "var(--shadow-volt)" : "var(--shadow-card)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function Toggle({ on, setOn }: { on: boolean; setOn: (v: boolean) => void }) {
  return (
    <button
      onClick={() => setOn(!on)}
      style={{
        width: 42,
        height: 24,
        borderRadius: 99,
        border: "none",
        cursor: "pointer",
        padding: 3,
        background: on ? "var(--volt)" : "var(--obsidian-3)",
        transition: "background .16s",
        display: "flex",
        justifyContent: on ? "flex-end" : "flex-start",
        boxShadow: on ? "var(--shadow-volt-sm)" : "none",
      }}
    >
      <span
        style={{ width: 18, height: 18, borderRadius: "50%", background: on ? "var(--void)" : "var(--silver)" }}
      />
    </button>
  );
}

/* Real multicolor Google "G" mark (sign-in). */
export function GoogleG({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" style={{ display: "block", flexShrink: 0 }}>
      <path
        fill="#FFC107"
        d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z"
      />
      <path
        fill="#FF3D00"
        d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238C29.211 35.091 26.715 36 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.611 20.083H42V20H24v8h11.303c-.792 2.237-2.231 4.166-4.087 5.571l6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z"
      />
    </svg>
  );
}
