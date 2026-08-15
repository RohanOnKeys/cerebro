import type { Metadata } from "next";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { MeetingsPanel } from "@/components/dashboard/MeetingsPanel";
import { PastMeetingsPanel } from "@/components/dashboard/PastMeetingsPanel";
import { getDashboardData } from "@/lib/api";

export const metadata: Metadata = {
  title: "Meetings",
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

export default async function MeetingsPage() {
  const data = await getDashboardData();
  const meetings = data.upcomingMeetings;

  const meetingsToday = meetings.filter((m) => isToday(m.startsAt)).length;
  const avgRsvpRate = meetings.length
    ? Math.round(
        (meetings.reduce((sum, m) => sum + m.attendeesConfirmed / m.attendeesTotal, 0) /
          meetings.length) *
          100,
      )
    : 0;

  const stats = [
    { value: meetingsToday, label: "Meetings today" },
    { value: meetings.length, label: "This week" },
    { value: `${avgRsvpRate}%`, label: "Avg RSVP rate" },
    { value: data.scheduledReminders.length, label: "Reminders scheduled" },
  ];

  return (
    <DashboardShell active="meetings" stats={stats}>
      <MeetingsPanel meetings={meetings} reminders={data.scheduledReminders} />
      <PastMeetingsPanel meetings={data.pastMeetings} />
    </DashboardShell>
  );
}
