"use client";

import { useState } from "react";

interface Row {
  copy: string;
  action: string;
  confirmMessage: string;
  endpoint: string;
}

const ROWS: Row[] = [
  {
    copy: "Revoke access for a connected integration.",
    action: "Revoke access",
    confirmMessage: "Revoke channel access? This can be reconnected later, but every channel will show as disconnected until then.",
    endpoint: "/api/organization/revoke-access",
  },
  {
    copy: "Deactivate this workspace's integration entirely.",
    action: "Deactivate",
    confirmMessage: "Deactivate this workspace's integration entirely? This is a workspace-wide action.",
    endpoint: "/api/organization/deactivate",
  },
];

function DangerRow({ row }: { row: Row }) {
  const [state, setState] = useState<"idle" | "pending" | "done" | "error">("idle");

  async function run() {
    if (!window.confirm(row.confirmMessage)) return;
    setState("pending");
    try {
      const res = await fetch(row.endpoint, { method: "POST" });
      if (!res.ok) throw new Error();
      setState("done");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="grid grid-cols-1 items-center gap-3 py-5 sm:grid-cols-[1fr_auto]">
      <span className="text-sm text-cerebro-muted">
        {row.copy}
        {state === "done" && <span className="ml-3 text-cerebro-danger">Done.</span>}
        {state === "error" && (
          <span className="ml-3 text-cerebro-danger">Failed — try again.</span>
        )}
      </span>
      <button
        type="button"
        disabled={state === "pending" || state === "done"}
        onClick={run}
        className="w-fit border border-cerebro-border px-4 py-2 text-xs font-medium text-cerebro-danger transition-colors hover:border-cerebro-danger disabled:cursor-not-allowed disabled:opacity-50"
      >
        {state === "pending" ? "Working…" : state === "done" ? "Done" : row.action}
      </button>
    </div>
  );
}

// Deliberately not <Panel>: the design calls this out as set apart with
// only a thin top divider and a plain (non-metallic) title — no gradient
// text, no glow, nothing that reads as an inviting/branded action.
export function DangerZonePanel() {
  return (
    <section className="py-10">
      <h2 className="text-lg font-semibold text-cerebro-ink">Danger zone</h2>
      <div className="mt-5 divide-y divide-cerebro-border border-t border-cerebro-border">
        {ROWS.map((row) => (
          <DangerRow key={row.action} row={row} />
        ))}
      </div>
    </section>
  );
}
