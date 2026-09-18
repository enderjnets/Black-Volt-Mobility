import { Suspense } from "react";

import { DemandPage } from "@/components/bv/dash/demand/DemandPage";

export const dynamic = "force-dynamic";

export default function DemandRoute() {
  return (
    <Suspense fallback={null}>
      <DemandPage />
    </Suspense>
  );
}
