import type { Metadata } from "next";
import { ActiveProjectsPanel } from "@/components/dashboard/ActiveProjectsPanel";
import { ChannelStatusPanel } from "@/components/dashboard/ChannelStatusPanel";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { PendingApprovalsPreview } from "@/components/dashboard/PendingApprovalsPreview";
import { UpcomingMeetingsPreview } from "@/components/dashboard/UpcomingMeetingsPreview";
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
export default async function DashboardOverviewPage() {
  const data = await getDashboardData();

  return (
    <DashboardShell active="dashboard" stats={data.statStrip}>
      <ChannelStatusPanel channels={data.channelStatuses} />
      <ActiveProjectsPanel
        projects={data.activeProjects}
        limit={4}
        viewAllHref="/dashboard/projects"
      />

      <div className="grid grid-cols-1 gap-x-14 gap-y-10 py-10 sm:grid-cols-2">
        <PendingApprovalsPreview
          approvals={data.pendingApprovals.slice(0, 3)}
          viewAllHref="/dashboard/members"
        />
        <UpcomingMeetingsPreview
          meetings={data.upcomingMeetings.slice(0, 3)}
          viewAllHref="/dashboard/meetings"
        />
      </div>
    </DashboardShell>
  );
}
