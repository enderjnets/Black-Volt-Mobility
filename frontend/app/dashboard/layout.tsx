import { DashShell } from "@/components/bv/dash/DashShell";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <DashShell>{children}</DashShell>;
}
