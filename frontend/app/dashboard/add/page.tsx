import { Suspense } from "react";

import { AddRide } from "@/components/bv/dash/AddRide";

// AddRide reads query params (useSearchParams) for client prefill.
export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <AddRide />
    </Suspense>
  );
}
