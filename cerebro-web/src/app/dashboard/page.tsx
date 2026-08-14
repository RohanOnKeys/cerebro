import type { Metadata } from "next";
import { ActiveProjectsPanel } from "@/components/dashboard/ActiveProjectsPanel";
import { AllowlistPanel } from "@/components/dashboard/AllowlistPanel";
import { ChannelStatusPanel } from "@/components/dashboard/ChannelStatusPanel";
import { CiRunsPanel } from "@/components/dashboard/CiRunsPanel";
import { LedgerPanel } from "@/components/dashboard/LedgerPanel";
import { MeetingsPanel } from "@/components/dashboard/MeetingsPanel";
import { MembersRolesPanel } from "@/components/dashboard/MembersRolesPanel";
import { MockDataBanner } from "@/components/dashboard/MockDataBanner";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { StatStrip } from "@/components/dashboard/StatStrip";
import { TopBar } from "@/components/dashboard/TopBar";
import { getDashboardData } from "@/lib/api";

export const metadata: Metadata = {
  title: "Team dashboard",
};

// Force-dynamic: this page always renders at request time, never at build
// time. That decouples `next build`/deploy from the backend's availability
// (a build never fails because the admin API happened to be down), and
// guarantees every dashboard load reflects the current database state
// rather than a build-time or ISR-cached snapshot.
export const dynamic = "force-dynamic";

// Server Component: this function runs only on the server, at request time.
// CEREBRO_ADMIN_API_TOKEN never reaches the browser because nothing here
// has a "use client" directive.
export default async function DashboardPage() {
  const data = await getDashboardData();

  return (
    <div id="top" className="min-h-screen bg-cerebro-bg">
      <TopBar />
      {data.usingMockData && <MockDataBanner />}
      <StatStrip items={data.statStrip} />

      <div className="mx-auto flex max-w-8xl">
        <Sidebar />

        <main className="flex-1 px-10 py-8">
          <ChannelStatusPanel channels={data.channelStatuses} />
          <ActiveProjectsPanel projects={data.activeProjects} />
          <MembersRolesPanel
            members={data.members}
            pendingApprovals={data.pendingApprovals}
          />
          <MeetingsPanel
            meetings={data.upcomingMeetings}
            reminders={data.scheduledReminders}
          />
          <CiRunsPanel runs={data.ciRuns} />
          <LedgerPanel entries={data.ledgerEntries} />
          <AllowlistPanel rows={data.allowlist} />
        </main>
      </div>
    </div>
  );
}
