/* Build a universal Google Maps directions URL to a destination address. Opens
   the native Maps app on mobile (iOS offers Apple Maps / Google Maps), the web
   app on desktop. No API key required. */
export function mapsDirectionsUrl(dest: string): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(
    (dest || "").trim(),
  )}&travelmode=driving`;
}

/* Open the maps directions to `dest` in a new tab / the native app. */
export function openMapsTo(dest: string): void {
  if (!dest || !dest.trim()) return;
  window.open(mapsDirectionsUrl(dest), "_blank", "noopener,noreferrer");
}
