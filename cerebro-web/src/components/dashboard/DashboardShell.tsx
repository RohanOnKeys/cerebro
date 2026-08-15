import { Sidebar, type NavKey } from "@/components/dashboard/Sidebar";
import { StatStrip } from "@/components/dashboard/StatStrip";
import { TopBar } from "@/components/dashboard/TopBar";
import type { StatStripItem } from "@/lib/types";

export function DashboardShell({
  active,
  stats,
  children,
}: {
  active: NavKey;
  stats: StatStripItem[];
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-cerebro-bg">
      <TopBar />
      <StatStrip items={stats} />

      <div className="mx-auto flex max-w-8xl">
        <Sidebar active={active} />
        <main className="flex-1 px-10 py-8">{children}</main>
      </div>
    </div>
  );
}
