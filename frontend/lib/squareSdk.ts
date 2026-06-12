/* Loads the Square Web Payments SDK from the sandbox or production CDN exactly
   once. Shared by the booking card form and the driver subscription checkout so
   there is a single loader (and a single cached promise). */

let sdkPromise: Promise<void> | null = null;

export function loadSquareSdk(env: string): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("ssr"));
  if ((window as unknown as { Square?: unknown }).Square) return Promise.resolve();
  if (sdkPromise) return sdkPromise;
  const src =
    env === "production"
      ? "https://web.squarecdn.com/v1/square.js"
      : "https://sandbox.web.squarecdn.com/v1/square.js";
  sdkPromise = new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("square_sdk_load_failed"));
    document.head.appendChild(s);
  });
  return sdkPromise;
}

export type SquareCardObj = {
  attach: (el: HTMLElement) => Promise<void>;
  tokenize: () => Promise<{ status: string; token?: string }>;
};

export type SquarePayments = {
  payments: (appId: string, locId: string) => Promise<{ card: () => Promise<SquareCardObj> }>;
};
