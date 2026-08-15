"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { formatPopulation } from "@/lib/format";
import type { PendingApproval } from "@/lib/types";

export function PendingApprovalRow({ approval }: { approval: PendingApproval }) {
  const router = useRouter();
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);
  const [resolved, setResolved] = useState<"approved" | "rejected" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(action: "approve" | "reject") {
    setPending(action);
    setError(null);
    try {
      const res = await fetch(`/api/approvals/${approval.id}/${action}`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `${action} failed`);
      }
      setResolved(action === "approve" ? "approved" : "rejected");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} failed`);
    } finally {
      setPending(null);
    }
  }

  if (resolved) {
    return (
      <div className="grid grid-cols-1 items-center gap-3 py-5 sm:grid-cols-[1.2fr_1fr_1.2fr_auto] sm:gap-4">
        <span className="text-sm font-medium text-cerebro-muted line-through">
          {approval.name}
        </span>
        <span className="text-sm text-cerebro-muted">
          {resolved === "approved" ? "Approved" : "Rejected"}
        </span>
        <span />
        <span />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 items-center gap-3 py-5 sm:grid-cols-[1.2fr_1fr_1.2fr_auto] sm:gap-4">
      <span className="text-sm font-medium text-cerebro-ink">{approval.name}</span>
      <span className="text-sm text-cerebro-muted">
        Claiming {formatPopulation(approval.claimedRole)}
      </span>
      <span className="text-sm text-cerebro-muted">
        Approver: {approval.eligibleApprover}
      </span>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="flex gap-3">
          <button
            type="button"
            disabled={pending !== null}
            onClick={() => act("approve")}
            className="border border-cerebro-accent-light px-4 py-2 text-xs font-medium text-cerebro-accent-lightest transition-colors hover:bg-cerebro-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pending === "approve" ? "Approving…" : "Approve"}
          </button>
          <button
            type="button"
            disabled={pending !== null}
            onClick={() => act("reject")}
            className="border border-cerebro-border px-4 py-2 text-xs font-medium text-cerebro-muted transition-colors hover:text-cerebro-ink disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pending === "reject" ? "Rejecting…" : "Reject"}
          </button>
        </div>
        {error && <span className="text-xs text-cerebro-danger">{error}</span>}
      </div>
    </div>
  );
}
