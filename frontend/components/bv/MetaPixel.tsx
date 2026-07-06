/* Meta Pixel base loader. Renders nothing unless NEXT_PUBLIC_META_PIXEL_ID is set,
   so non-prod builds ship no tracker. The pixel id is public by design (it only
   identifies the ad account's dataset); the CAPI access token is server-only.
   Funnel events (InitiateCheckout / QuoteViewed / Purchase) are fired from the
   booking flow via lib/analytics `pixel()`, deduped against the server CAPI by
   a shared eventID. */
import Script from "next/script";

import { PixelSdkLoader } from "./PixelSdkLoader";

const PIXEL_ID = process.env.NEXT_PUBLIC_META_PIXEL_ID;

export function MetaPixel() {
  if (!PIXEL_ID) return null;
  return (
    <>
      {/* Split load: the tiny fbq STUB runs right after hydration (zero network) so
          every funnel call — PageView, QuoteViewed, InitiateCheckout — is queued from
          the first moment; the ~242KB fbevents.js SDK loads on first interaction (or a
          timeout) via PixelSdkLoader, out of the LCP window, and drains the queue. */}
      <Script id="meta-pixel-stub" strategy="afterInteractive">
        {`!function(f){if(f.fbq)return;var n=f.fbq=function(){n.callMethod?
        n.callMethod.apply(n,arguments):n.queue.push(arguments)};
        if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
        n.queue=[]}(window);
        fbq('init','${PIXEL_ID}');fbq('track','PageView');`}
      </Script>
      <PixelSdkLoader />
      <noscript>
        {/* eslint-disable-next-line @next/next/no-img-element -- tracking pixel, not an image */}
        <img
          height="1"
          width="1"
          style={{ display: "none" }}
          alt=""
          src={`https://www.facebook.com/tr?id=${PIXEL_ID}&ev=PageView&noscript=1`}
        />
      </noscript>
    </>
  );
}
