import { formatDate, formatPopulation } from "@/lib/format";
import type { Member, PendingApproval } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

export function MembersRolesPanel({
  members,
  pendingApprovals,
}: {
  members: Member[];
  pendingApprovals: PendingApproval[];
}) {
  return (
    <Panel id="members" title="Members and roles">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-cerebro-border text-cerebro-muted">
            <th className="pb-3 font-medium">Name</th>
            <th className="pb-3 font-medium">Role</th>
            <th className="pb-3 font-medium">Verified channels</th>
            <th className="pb-3 font-medium">Joined</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-cerebro-border">
          {members.map((member) => (
            <tr key={member.id}>
              <td className="py-4 font-medium text-cerebro-ink">{member.name}</td>
              <td className="py-4 text-cerebro-muted">{formatPopulation(member.population)}</td>
              <td className="py-4 text-cerebro-muted">{member.channelBindingCount}</td>
              <td className="py-4 text-cerebro-muted">{formatDate(member.joinedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-10 border-t border-cerebro-border pt-8">
        <h3 className="font-display text-base font-semibold text-cerebro-ink">
          Pending approvals
        </h3>

        <div className="mt-5 divide-y divide-cerebro-border border-y border-cerebro-border">
          {pendingApprovals.map((approval) => (
            <div
              key={approval.id}
              className="grid grid-cols-1 items-center gap-3 py-5 sm:grid-cols-[1.2fr_1fr_1.2fr_auto] sm:gap-4"
            >
              <span className="text-sm font-medium text-cerebro-ink">{approval.name}</span>
              <span className="text-sm text-cerebro-muted">
                Claiming {formatPopulation(approval.claimedRole)}
              </span>
              <span className="text-sm text-cerebro-muted">
                Approver: {approval.eligibleApprover}
              </span>
              <div className="flex gap-3">
                <button
                  type="button"
                  className="border border-cerebro-accent-light px-4 py-2 text-xs font-medium text-cerebro-accent-lightest transition-colors hover:bg-cerebro-accent"
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="border border-cerebro-border px-4 py-2 text-xs font-medium text-cerebro-muted transition-colors hover:text-cerebro-ink"
                >
                  Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}
