import { formatPopulation } from "@/lib/format";
import type { PendingApproval } from "@/lib/types";
import { ViewAllLink } from "@/components/dashboard/ViewAllLink";

// Deliberately not wrapped in <Panel>: this renders as one half of a
// two-column row (see the dashboard overview page), so it can't own its
// own full-width border-bottom/padding the way a stacked Panel does.
export function PendingApprovalsPreview({
  approvals,
  viewAllHref,
}: {
  approvals: PendingApproval[];
  viewAllHref: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-metallic font-display text-xl font-semibold">Pending approvals</h2>
        <ViewAllLink href={viewAllHref} />
      </div>
      <div className="mt-2 h-px w-full bg-cerebro-border" aria-hidden="true" />

      <div className="mt-8 divide-y divide-cerebro-border border-y border-cerebro-border">
        {approvals.map((approval) => (
          <div key={approval.id} className="py-4">
            <p className="text-sm font-medium text-cerebro-ink">{approval.name}</p>
            <p className="mt-1 text-xs text-cerebro-muted">
              Claimed {formatPopulation(approval.claimedRole)} · approver {approval.eligibleApprover}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
