import type { AllowlistRow, Population } from "@/lib/types";
import { formatPopulation } from "@/lib/format";
import { Panel } from "@/components/dashboard/Panel";

const ROLES: Population[] = ["client", "ops", "dev", "lead", "admin"];

export function AllowlistPanel({ rows }: { rows: AllowlistRow[] }) {
  return (
    <Panel id="allowlist" title="Allowlist and access">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-cerebro-border text-cerebro-muted">
            <th className="pb-3 font-medium">Tool</th>
            {ROLES.map((role) => (
              <th key={role} className="pb-3 text-center font-medium">
                {formatPopulation(role)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-cerebro-border">
          {rows.map((row) => (
            <tr key={row.tool}>
              <td className="py-4 font-medium text-cerebro-ink">{row.tool}</td>
              {ROLES.map((role) => (
                <td key={role} className="py-4 text-center text-cerebro-accent-lightest">
                  {row.populations[role] ? "✓" : ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}
