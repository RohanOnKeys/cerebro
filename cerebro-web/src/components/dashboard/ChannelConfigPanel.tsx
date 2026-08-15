import type { ChannelConfig } from "@/lib/types";
import { ChannelConfigRow } from "@/components/dashboard/ChannelConfigRow";
import { Panel } from "@/components/dashboard/Panel";

export function ChannelConfigPanel({ configs }: { configs: ChannelConfig[] }) {
  return (
    <Panel title="Channel configuration">
      <div className="divide-y divide-cerebro-border border-y border-cerebro-border">
        {configs.map((config) => (
          <ChannelConfigRow key={config.channel} config={config} />
        ))}
      </div>
    </Panel>
  );
}
