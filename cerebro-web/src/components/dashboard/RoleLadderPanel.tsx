import type { Member, Population } from "@/lib/types";
import { formatPopulation } from "@/lib/format";
import { Panel } from "@/components/dashboard/Panel";

const LADDER: Exclude<Population, "client">[] = ["ops", "dev", "lead", "admin"];

export function RoleLadderPanel({ members }: { members: Member[] }) {
  const counts = LADDER.map((role) => ({
    role,
    count: members.filter((m) => m.population === role).length,
  }));

  return (
    <Panel title="Role ladder">
      <div className="flex items-center">
        {counts.map((step, index) => (
          <div key={step.role} className="flex flex-1 items-center last:flex-none">
            <div className="flex min-w-[140px] flex-col items-center gap-2.5 text-center">
              <div className="h-4 w-4 bg-cerebro-accent-light" aria-hidden="true" />
              <span className="text-base font-medium text-cerebro-ink">{formatPopulation(step.role)}</span>
              <span className="text-xs text-cerebro-muted">{step.count} members</span>
            </div>
            {index < counts.length - 1 && (
              <div className="mb-9 h-px flex-1 bg-cerebro-border" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
