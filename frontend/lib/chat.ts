/* Client helpers for the Joules chat API (same-origin /api → backend). */
import { ApiError, fmtApiDetail } from "./booking";

export interface ChatApiMsg {
  id: number;
  role: "user" | "assistant" | "owner";
  body: string;
  created_at: string;
}

export interface ChatHistory {
  conversation_id: number | null;
  status: string | null;
  messages: ChatApiMsg[];
}

export interface ChatSendResult {
  reply: string;
  escalated: boolean;
  conversation_id: number;
}

export interface ChatThread {
  id: number;
  client_name: string | null;
  client_email: string | null;
  client_phone: string | null;
  status: string;
  unread: number;
  last_message_at: string;
  snippet: string;
}

export interface ChatThreadDetail {
  id: number;
  status: string;
  client_name: string | null;
  client_email: string | null;
  client_phone: string | null;
  messages: ChatApiMsg[];
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new ApiError(`${path}:${r.status}`, r.status);
  return r.json();
}

async function jsend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(fmtApiDetail((d as { detail?: unknown }).detail, `${path}:${r.status}`), r.status);
  }
  return r.json();
}

// ─── Passenger ────────────────────────────────────────────────────────────────

export function getChat(): Promise<ChatHistory> {
  return jget<ChatHistory>("/v1/chat");
}

export function sendChatMessage(message: string, lang: string): Promise<ChatSendResult> {
  return jsend<ChatSendResult>("/v1/chat/messages", "POST", { message, lang });
}

// ─── Staff (dashboard) ──────────────────────────────────────────────────────────

export function listThreads(status?: string): Promise<ChatThread[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return jget<ChatThread[]>(`/v1/chat/threads${q}`);
}

export function getThread(id: number): Promise<ChatThreadDetail> {
  return jget<ChatThreadDetail>(`/v1/chat/threads/${id}`);
}

export function closeThread(id: number): Promise<{ ok: boolean; status: string }> {
  return jsend<{ ok: boolean; status: string }>(`/v1/chat/threads/${id}/close`, "POST");
}
