import { formatTimestamp } from "@/lib/format";
import type { ChannelStatus } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

const CHANNEL_LABEL: Record<ChannelStatus["channel"], string> = {
  telegram: "Telegram",
  discord: "Discord",
  slack: "Slack",
  email: "Email",
};

export function ChannelStatusPanel({ channels }: { channels: ChannelStatus[] }) {
  return (
    <Panel id="channels" title="Channel status">
      <div className="divide-y divide-cerebro-border border-y border-cerebro-border">
        {channels.map((channel) => (
          <div
            key={channel.channel}
            className="grid grid-cols-2 items-center gap-4 py-5 sm:grid-cols-4"
          >
            <span className="text-base font-medium text-cerebro-ink">
              {CHANNEL_LABEL[channel.channel]}
            </span>
            <span
              className={
                channel.state === "live"
                  ? "w-fit bg-cerebro-success px-2.5 py-1 text-xs font-medium text-cerebro-bg"
                  : "w-fit border border-cerebro-danger px-2.5 py-1 text-xs font-medium text-cerebro-danger"
              }
            >
              {channel.state === "live" ? "Live" : "Reconnect needed"}
            </span>
            <span className="text-sm text-cerebro-muted">
              Last verified {formatTimestamp(channel.lastVerifiedMessageAt)}
            </span>
            <span className="text-sm text-cerebro-muted">
              {channel.messagesToday.toLocaleString()} messages today
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
