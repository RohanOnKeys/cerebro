import { formatDate, formatPopulation } from "@/lib/format";
import type { Member, PendingApproval } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";
import { PendingApprovalRow } from "@/components/dashboard/PendingApprovalRow";

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
            <PendingApprovalRow key={approval.id} approval={approval} />
          ))}
        </div>
      </div>
    </Panel>
  );
}
