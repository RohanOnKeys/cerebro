import type { Metadata } from "next";
import { AllowlistPanel } from "@/components/dashboard/AllowlistPanel";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { RoleLadderPanel } from "@/components/dashboard/RoleLadderPanel";
import { getDashboardData } from "@/lib/api";

export const metadata: Metadata = {
  title: "Roles",
};

export const dynamic = "force-dynamic";

export default async function RolesPage() {
  const data = await getDashboardData();
  const members = data.members;

  const stats = [
    { value: 4, label: "Total roles" },
    { value: members.filter((m) => m.population === "ops").length, label: "Ops" },
    {
      value: members.filter((m) => m.population === "dev" || m.population === "lead").length,
      label: "Dev / Lead",
    },
    { value: members.filter((m) => m.population === "admin").length, label: "Admin" },
  ];

  return (
    <DashboardShell active="roles" stats={stats} usingMockData={data.usingMockData}>
      <RoleLadderPanel members={members} />
      <AllowlistPanel rows={data.allowlist} />
    </DashboardShell>
  );
}
