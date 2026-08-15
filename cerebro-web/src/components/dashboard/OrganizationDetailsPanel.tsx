import type { OrganizationInfo } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

const ROW_HELP: Record<string, string> = {
  "Team join code":
    "Give this to new clients or teammates — it's the first thing they're asked for on any channel, and routes them into this org.",
};

export function OrganizationDetailsPanel({ organization }: { organization: OrganizationInfo }) {
  const rows: { label: string; value: string; mono?: boolean }[] = [
    { label: "Organization name", value: organization.name },
    { label: "Admin contact", value: organization.adminContact },
    { label: "Billing tier", value: organization.billingTier },
    { label: "Team join code", value: organization.joinCode, mono: true },
  ];

  return (
    <Panel title="Organization details">
      <div className="divide-y divide-cerebro-border border-y border-cerebro-border">
        {rows.map((row) => (
          <div
            key={row.label}
            className="grid grid-cols-1 items-start gap-2 py-5 sm:grid-cols-[280px_1fr]"
          >
            <span className="text-base font-medium text-cerebro-ink">{row.label}</span>
            <div>
              <span
                className={`text-sm text-cerebro-muted ${row.mono ? "font-mono tracking-widest text-cerebro-accent-lightest" : ""}`}
              >
                {row.value}
              </span>
              {ROW_HELP[row.label] && (
                <p className="mt-1 text-xs text-cerebro-muted">{ROW_HELP[row.label]}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
