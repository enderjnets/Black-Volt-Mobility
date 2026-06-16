/* Driver sales-funnel ("My Stats") API client. Staff-only, tenant-scoped. */

import { fmtApiDetail } from "./booking";

export interface FunnelRate {
  num: number;
  den: number;
  point: number;
  low: number;
  high: number;
  low_data: boolean;
}

export interface FunnelGoal {
  target_weekly_revenue: number | null;
  target_monthly_clients: number | null;
  working_days_per_week: number;
  currency: string;
}

export interface Projection {
  horizon_days: number;
  working_days: number;
  conversations_per_day: number;
  expected_clients: number;
  expected_clients_low: number;
  expected_clients_high: number;
  expected_revenue: number;
  expected_revenue_low: number;
  expected_revenue_high: number;
}

export interface FunnelLog {
  date: string;
  conversations: number;
  pitches: number;
  contacts: number;
  notes: string | null;
}

export interface FunnelSummary {
  days: number;
  today: string;
  totals: {
    conversations: number;
    pitches: number;
    contacts: number;
    clients: number;
    revenue: number;
    logged_days: number;
  };
  rates: {
    pitch: FunnelRate;
    contact: FunnelRate;
    convert: FunnelRate;
    overall_point: number;
    overall_low: number;
    overall_high: number;
  };
  value_per_client: number | null;
  avg_fare: number;
  has_earnings: boolean;
  timeseries: { date: string; day: string; conversations: number; revenue: number }[];
  streak: number;
  today_log: FunnelLog | null;
  week: { conversations: number; clients: number; revenue: number };
  goal: FunnelGoal;
  projection: { pace_per_day: number; week: Projection; month: Projection };
}

export interface ProjectResult {
  period: string;
  ok: boolean;
  revenue_unknown?: boolean;
  value_per_client: number | null;
  target_clients?: number;
  working_days?: number;
  required?: {
    conversations: number;
    pitches: number;
    contacts: number;
    conversations_per_day: number;
    conversations_per_day_low: number;
    conversations_per_day_high: number;
  };
  rates?: { overall_point: number; low_data: boolean };
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error(`${path}:${r.status}`);
  return r.json();
}

async function jsend<T>(path: string, method: string, body: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(fmtApiDetail((d as { detail?: unknown }).detail, `${path}:${r.status}`));
  }
  return r.json();
}

export async function getFunnelSummary(days = 30): Promise<FunnelSummary> {
  return jget<FunnelSummary>(`/v1/stats/funnel?days=${days}`);
}

export async function saveFunnelLog(body: {
  date?: string;
  conversations: number;
  pitches: number;
  contacts: number;
  notes?: string | null;
}): Promise<FunnelLog> {
  return jsend<FunnelLog>("/v1/stats/funnel/log", "POST", body);
}

export async function setFunnelGoal(body: {
  target_weekly_revenue: number | null;
  target_monthly_clients: number | null;
  working_days_per_week: number;
}): Promise<FunnelGoal> {
  return jsend<FunnelGoal>("/v1/stats/funnel/goal", "PUT", body);
}

export async function projectGoal(body: {
  period: string;
  target_revenue?: number | null;
  target_clients?: number | null;
}): Promise<ProjectResult> {
  return jsend<ProjectResult>("/v1/stats/funnel/project", "POST", body);
}
