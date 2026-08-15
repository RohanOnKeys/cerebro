import type { Metadata } from "next";
import { CiRunsPanel } from "@/components/dashboard/CiRunsPanel";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { formatDuration } from "@/lib/format";
import { getDashboardData } from "@/lib/api";

export const metadata: Metadata = {
  title: "CI runs",
};

export const dynamic = "force-dynamic";

function isToday(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export default async function CiRunsPage() {
  const data = await getDashboardData();
  const runs = data.ciRuns;

  const runsToday = runs.filter((r) => isToday(r.finishedAt)).length;
  const avgDuration = runs.length
    ? Math.round(runs.reduce((sum, r) => sum + r.durationSeconds, 0) / runs.length)
    : 0;

  const stats = [
    { value: runsToday, label: "Runs today" },
    { value: runs.filter((r) => r.result === "passed").length, label: "Passed" },
    { value: runs.filter((r) => r.result === "failed").length, label: "Failed" },
    { value: formatDuration(avgDuration), label: "Avg duration" },
  ];

  return (
    <DashboardShell active="ci-runs" stats={stats} usingMockData={data.usingMockData}>
      <CiRunsPanel runs={runs} />
    </DashboardShell>
  );
}
