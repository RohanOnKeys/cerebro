import { formatTimestamp } from "@/lib/format";
import type { LedgerEntry } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

export function LedgerPanel({ entries }: { entries: LedgerEntry[] }) {
  return (
    <Panel id="ledger" title="Ledger">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-cerebro-border text-cerebro-muted">
            <th className="pb-3 font-medium">Who asked</th>
            <th className="pb-3 font-medium">What ran</th>
            <th className="pb-3 font-medium">What it returned</th>
            <th className="pb-3 font-medium">When</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-cerebro-border">
          {entries.map((entry) => (
            <tr key={entry.id}>
              <td className="py-4 font-medium text-cerebro-ink">{entry.principal}</td>
              <td className="py-4 text-cerebro-muted">{entry.action}</td>
              <td className="py-4 text-cerebro-muted">{entry.result}</td>
              <td className="py-4 text-cerebro-muted">{formatTimestamp(entry.at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}
