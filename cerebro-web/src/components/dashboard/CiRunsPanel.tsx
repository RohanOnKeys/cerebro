import { formatDuration, formatTimestamp } from "@/lib/format";
import type { CiResult, CiRun } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

const RESULT_LABEL: Record<CiResult, string> = {
  passed: "Passed",
  failed: "Failed",
  cancelled: "Cancelled",
};

// Thin left border only, per spec: "no colored status dots, result
// communicated by text label plus a thin left border in a supporting
// accent shade."
const RESULT_BORDER: Record<CiResult, string> = {
  passed: "border-l-cerebro-success",
  failed: "border-l-cerebro-danger",
  cancelled: "border-l-cerebro-border",
};

const RESULT_TEXT: Record<CiResult, string> = {
  passed: "text-cerebro-success",
  failed: "text-cerebro-danger",
  cancelled: "text-cerebro-muted",
};

export function CiRunsPanel({ runs }: { runs: CiRun[] }) {
  return (
    <Panel id="ci-runs" title="CI runs">
      <div className="divide-y divide-cerebro-border border-y border-cerebro-border">
        {runs.map((run) => (
          <div
            key={run.id}
            className={`grid grid-cols-1 gap-2 border-l-2 py-5 pl-4 sm:grid-cols-[1fr_1.2fr_1fr_0.8fr_0.7fr_1fr] sm:items-center sm:gap-4 ${RESULT_BORDER[run.result]}`}
          >
            <span className="text-sm font-medium text-cerebro-ink">{run.repo}</span>
            <span className="text-sm text-cerebro-muted">{run.workflowName}</span>
            <span className="text-sm text-cerebro-muted">{run.triggeredBy}</span>
            <span className={`text-sm ${RESULT_TEXT[run.result]}`}>{RESULT_LABEL[run.result]}</span>
            <span className="text-sm text-cerebro-muted">{formatDuration(run.durationSeconds)}</span>
            <span className="text-sm text-cerebro-muted">{formatTimestamp(run.finishedAt)}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
