import { formatReminderStage, formatTimestamp } from "@/lib/format";
import type { ScheduledReminder, UpcomingMeeting } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

const PROVIDER_LABEL: Record<UpcomingMeeting["provider"], string> = {
  google_meet: "Google Meet",
  zoom: "Zoom",
};

export function MeetingsPanel({
  meetings,
  reminders,
}: {
  meetings: UpcomingMeeting[];
  reminders: ScheduledReminder[];
}) {
  return (
    <Panel id="meetings" title="Meetings and reminders">
      <div className="divide-y divide-cerebro-border border-y border-cerebro-border">
        {meetings.map((meeting) => (
          <div
            key={meeting.id}
            className="grid grid-cols-1 gap-2 py-5 sm:grid-cols-[1.4fr_1fr_1fr_1fr_1fr] sm:items-center sm:gap-4"
          >
            <span className="text-base font-medium text-cerebro-ink">{meeting.title}</span>
            <span className="text-sm text-cerebro-muted">{formatTimestamp(meeting.startsAt)}</span>
            <span className="text-sm text-cerebro-muted">Organizer: {meeting.organizer}</span>
            <span className="text-sm text-cerebro-muted">{PROVIDER_LABEL[meeting.provider]}</span>
            <span className="text-sm text-cerebro-accent-lightest">
              {meeting.attendeesConfirmed} of {meeting.attendeesTotal} confirmed
            </span>
          </div>
        ))}
      </div>

      <div className="mt-10 border-t border-cerebro-border pt-8">
        <h3 className="font-display text-base font-semibold text-cerebro-ink">
          Scheduled reminders
        </h3>
        <div className="mt-5 divide-y divide-cerebro-border border-y border-cerebro-border">
          {reminders.map((reminder) => (
            <div key={reminder.id} className="flex items-center justify-between py-4">
              <span className="text-sm text-cerebro-ink">{reminder.meetingTitle}</span>
              <span className="text-sm text-cerebro-muted">{formatReminderStage(reminder.stage)}</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}
