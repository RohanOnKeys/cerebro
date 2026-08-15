import type { Metadata } from "next";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { MembersRolesPanel } from "@/components/dashboard/MembersRolesPanel";
import { getDashboardData } from "@/lib/api";

export const metadata: Metadata = {
  title: "Members",
};

export const dynamic = "force-dynamic";

export default async function MembersPage() {
  const data = await getDashboardData();
  const members = data.members;

  const stats = [
    { value: members.length, label: "Total members" },
    { value: members.filter((m) => m.population === "ops").length, label: "Ops" },
    {
      value: members.filter((m) => m.population === "dev" || m.population === "lead").length,
      label: "Dev / Lead",
    },
    { value: members.filter((m) => m.population === "admin").length, label: "Admins" },
    { value: data.pendingApprovals.length, label: "Pending approvals" },
  ];

  return (
    <DashboardShell active="members" stats={stats} usingMockData={data.usingMockData}>
      <MembersRolesPanel members={members} pendingApprovals={data.pendingApprovals} />
    </DashboardShell>
  );
}
