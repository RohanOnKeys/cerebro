import type { Metadata } from "next";
import { ActiveProjectsPanel } from "@/components/dashboard/ActiveProjectsPanel";
import { AllowlistPanel } from "@/components/dashboard/AllowlistPanel";
import { ChannelStatusPanel } from "@/components/dashboard/ChannelStatusPanel";
import { CiRunsPanel } from "@/components/dashboard/CiRunsPanel";
import { LedgerPanel } from "@/components/dashboard/LedgerPanel";
import { MeetingsPanel } from "@/components/dashboard/MeetingsPanel";
import { MembersRolesPanel } from "@/components/dashboard/MembersRolesPanel";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { StatStrip } from "@/components/dashboard/StatStrip";
import { TopBar } from "@/components/dashboard/TopBar";
import {
  getActiveProjects,
  getAllowlist,
  getChannelStatuses,
  getCiRuns,
  getLedgerEntries,
  getMembers,
  getPendingApprovals,
  getScheduledReminders,
  getStatStrip,
  getUpcomingMeetings,
  isLiveApiConfigured,
} from "@/lib/api";

export const metadata: Metadata = {
  title: "Team dashboard",
};

// Data comes from src/lib/api.ts. With no Admin/Read API base URL configured,
// api.ts returns typed mock data (src/lib/mock-data.ts). Panel components
// already take props — flipping to live data is an env + API change only.
export default async function DashboardPage() {
  const [
    stats,
    channels,
    projects,
    members,
    pendingApprovals,
    meetings,
    reminders,
    runs,
    ledger,
    allowlist,
  ] = await Promise.all([
    getStatStrip(),
    getChannelStatuses(),
    getActiveProjects(),
    getMembers(),
    getPendingApprovals(),
    getUpcomingMeetings(),
    getScheduledReminders(),
    getCiRuns(),
    getLedgerEntries(),
    getAllowlist(),
  ]);

  return (
    <div id="top" className="min-h-screen bg-cerebro-bg">
      <TopBar />
      <StatStrip items={stats} />
      {!isLiveApiConfigured() ? (
        <p className="border-b border-cerebro-border px-8 py-3 text-xs text-cerebro-muted">
          Showing typed mock data — set{" "}
          <code className="text-cerebro-accent-lightest">NEXT_PUBLIC_CEREBRO_API_BASE_URL</code>{" "}
          when the Admin/Read API is available.
        </p>
      ) : null}

      <div className="mx-auto flex max-w-8xl">
        <Sidebar />

        <main className="flex-1 px-10 py-8">
          <ChannelStatusPanel channels={channels} />
          <ActiveProjectsPanel projects={projects} />
          <MembersRolesPanel members={members} pendingApprovals={pendingApprovals} />
          <MeetingsPanel meetings={meetings} reminders={reminders} />
          <CiRunsPanel runs={runs} />
          <LedgerPanel entries={ledger} />
          <AllowlistPanel rows={allowlist} />
        </main>
      </div>
    </div>
  );
}
