import { formatTimestamp } from "@/lib/format";
import type { UpcomingMeeting } from "@/lib/types";
import { ViewAllLink } from "@/components/dashboard/ViewAllLink";

// Deliberately not wrapped in <Panel>: see PendingApprovalsPreview — this is
// the other half of the same two-column row on the dashboard overview.
export function UpcomingMeetingsPreview({
  meetings,
  viewAllHref,
}: {
  meetings: UpcomingMeeting[];
  viewAllHref: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-metallic font-display text-xl font-semibold">Upcoming meetings</h2>
        <ViewAllLink href={viewAllHref} />
      </div>
      <div className="mt-2 h-px w-full bg-cerebro-border" aria-hidden="true" />

      <div className="mt-8 divide-y divide-cerebro-border border-y border-cerebro-border">
        {meetings.map((meeting) => (
          <div key={meeting.id} className="py-4">
            <p className="text-sm font-medium text-cerebro-ink">{meeting.title}</p>
            <p className="mt-1 text-xs text-cerebro-muted">
              {formatTimestamp(meeting.startsAt)} · {meeting.attendeesConfirmed} of {meeting.attendeesTotal} confirmed
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
