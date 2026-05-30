import { WebShell } from "@/components/bv/web/WebShell";

export default function WebLayout({ children }: { children: React.ReactNode }) {
  return <WebShell>{children}</WebShell>;
}
