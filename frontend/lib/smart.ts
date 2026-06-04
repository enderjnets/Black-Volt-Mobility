/* Client helper for the Smart reservation extraction API.
   Posts 1..N screenshots (multipart) → reservation fields the form pre-fills. */

export interface SmartExtraction {
  fields: Record<string, unknown>;
  simulated: boolean;
  image_count: number;
}

export async function extractReservation(files: File[]): Promise<SmartExtraction> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const r = await fetch("/api/v1/rides/extract", {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(typeof d.detail === "string" ? d.detail : `extract:${r.status}`);
  }
  return r.json();
}
