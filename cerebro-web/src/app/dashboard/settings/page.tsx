import type { Metadata } from "next";
import { ChannelConfigPanel } from "@/components/dashboard/ChannelConfigPanel";
import { DangerZonePanel } from "@/components/dashboard/DangerZonePanel";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { NotificationPreferencesPanel } from "@/components/dashboard/NotificationPreferencesPanel";
import { OrganizationDetailsPanel } from "@/components/dashboard/OrganizationDetailsPanel";
import { getDashboardData } from "@/lib/api";

export const metadata: Metadata = {
  title: "Settings",
};

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const data = await getDashboardData();

  const stats = [
    {
      value: data.channelConfig.filter((c) => c.apiKeyStatus === "configured").length,
      label: "Connected integrations",
    },
    { value: "—", label: "Last config change" },
  ];

  return (
    <DashboardShell active="settings" stats={stats}>
      <ChannelConfigPanel configs={data.channelConfig} />
      <NotificationPreferencesPanel preferences={data.notificationPreferences} />
      <OrganizationDetailsPanel organization={data.organization} />
      <DangerZonePanel />
    </DashboardShell>
  );
}
