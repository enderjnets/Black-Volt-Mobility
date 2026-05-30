import { AuthGuard } from "@/components/bv/dash/AuthGuard";
import { DashShell } from "@/components/bv/dash/DashShell";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <DashShell>{children}</DashShell>
    </AuthGuard>
  );
}
