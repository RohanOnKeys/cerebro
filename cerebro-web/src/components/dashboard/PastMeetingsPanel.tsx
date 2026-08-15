import { formatTimestamp } from "@/lib/format";
import type { PastMeeting } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

const PROVIDER_LABEL: Record<PastMeeting["provider"], string> = {
  google_meet: "Google Meet",
  zoom: "Zoom",
};

export function PastMeetingsPanel({ meetings }: { meetings: PastMeeting[] }) {
  return (
    <Panel title="Past meetings">
      <div className="divide-y divide-cerebro-border border-y border-cerebro-border">
        {meetings.map((meeting) => (
          <div
            key={meeting.id}
            className="grid grid-cols-1 gap-2 py-5 sm:grid-cols-[1.4fr_1fr_1fr_1fr] sm:items-center sm:gap-4"
          >
            <span className="text-base font-medium text-cerebro-muted">{meeting.title}</span>
            <span className="text-sm text-cerebro-muted/70">{formatTimestamp(meeting.endedAt)}</span>
            <span className="text-sm text-cerebro-muted/70">Organizer: {meeting.organizer}</span>
            <span className="text-sm text-cerebro-muted/70">{PROVIDER_LABEL[meeting.provider]}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
