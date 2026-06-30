/* Client helper for the Smart reservation extraction API.
   Posts 1..N screenshots (multipart) → reservation fields the form pre-fills.
   Images are normalized in the browser first (downscaled + re-encoded to a
   vision-friendly format) so it works the same from Android, iPhone, Mac or
   Linux regardless of the original format/size. */

export type ReservationFields = Record<string, unknown>;

// Multi-reservation result: the API groups screenshots by client into one or more
// reservations.
export interface SmartExtractionMulti {
  reservations: ReservationFields[];
  simulated: boolean;
  count: number;
}

// Single-reservation result (used when filling ONE existing ride — RideDetail).
export interface SmartExtraction {
  fields: ReservationFields;
  simulated: boolean;
}

// Carries a stable `code` so the UI can show an actionable message.
export class SmartError extends Error {
  code: string;
  constructor(code: string, message?: string) {
    super(message || code);
    this.code = code;
  }
}

const MAX_EDGE = 2200; // longest side after downscale — keeps text legible, size small
const CANVAS_TYPES = ["image/jpeg", "image/png", "image/webp", "image/bmp", ""];

// Draw the image onto a canvas, downscaling the long edge, and re-encode. Returns
// the original file untouched for formats we shouldn't rasterize (e.g. animated
// GIF). Rejects with SmartError("decode_failed") if the browser can't decode it
// (typically HEIC on Chrome/Firefox) so the caller can tell the user.
export function normalizeImage(file: File): Promise<File> {
  if (!CANVAS_TYPES.includes(file.type)) return Promise.resolve(file);
  return new Promise<File>((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const { width, height } = img;
        const scale = Math.min(1, MAX_EDGE / Math.max(width, height));
        const w = Math.max(1, Math.round(width * scale));
        const h = Math.max(1, Math.round(height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          URL.revokeObjectURL(url);
          resolve(file);
          return;
        }
        ctx.drawImage(img, 0, 0, w, h);
        // PNG keeps text crisp; fall back to JPEG when it would be heavy.
        const usePng = file.type === "image/png" && scale === 1 && file.size < 2_000_000;
        const outType = usePng ? "image/png" : "image/jpeg";
        canvas.toBlob(
          (blob) => {
            URL.revokeObjectURL(url);
            if (!blob) {
              resolve(file);
              return;
            }
            const ext = outType === "image/png" ? "png" : "jpg";
            resolve(new File([blob], `screenshot.${ext}`, { type: outType }));
          },
          outType,
          0.92,
        );
      } catch {
        URL.revokeObjectURL(url);
        resolve(file);
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new SmartError("decode_failed"));
    };
    img.src = url;
  });
}

export function hasAnyField(fields: Record<string, unknown>): boolean {
  return Object.values(fields).some((v) => v != null && String(v).trim() !== "");
}

async function postExtract(files: File[], merge: boolean): Promise<SmartExtractionMulti> {
  const fd = new FormData();
  for (const f of files) {
    let out = f;
    try {
      out = await normalizeImage(f);
    } catch (e) {
      if (e instanceof SmartError) throw e; // undecodable format → surface to UI
    }
    fd.append("files", out);
  }
  if (merge) fd.append("merge", "true");
  const r = await fetch("/api/v1/rides/extract", {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new SmartError(typeof d.detail === "string" ? d.detail : `http_${r.status}`);
  }
  return r.json();
}

// Upload screenshots → one or more reservations, grouped by client. For the
// Add-ride batch flow.
export async function extractReservations(files: File[]): Promise<SmartExtractionMulti> {
  return postExtract(files, false);
}

// Single-reservation convenience: forces a merged result and returns the first
// (or empty) reservation. Used by RideDetail to fill ONE existing ride.
export async function extractReservation(files: File[]): Promise<SmartExtraction> {
  const res = await postExtract(files, true);
  return { fields: res.reservations[0] ?? {}, simulated: res.simulated };
}
