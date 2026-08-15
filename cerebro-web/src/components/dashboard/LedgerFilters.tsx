"use client";

import { useMemo, useState } from "react";
import { LedgerPanel } from "@/components/dashboard/LedgerPanel";
import type { LedgerEntry } from "@/lib/types";

const DATE_RANGES = ["Last 7 days", "Last 30 days", "Last quarter"] as const;
type DateRange = (typeof DATE_RANGES)[number];

const RANGE_DAYS: Record<DateRange, number> = {
  "Last 7 days": 7,
  "Last 30 days": 30,
  "Last quarter": 90,
};

const ALL = "All";

const selectClasses =
  "border border-cerebro-border bg-cerebro-bg px-3.5 py-2.5 text-sm text-cerebro-ink focus:border-cerebro-accent-light focus:outline-none";

function toolFromAction(action: string): string {
  return action.split("(")[0] ?? action;
}

export function LedgerFilters({ entries }: { entries: LedgerEntry[] }) {
  const [actor, setActor] = useState<string>(ALL);
  const [tool, setTool] = useState<string>(ALL);
  const [range, setRange] = useState<DateRange>("Last 30 days");

  const actors = useMemo(
    () => Array.from(new Set(entries.map((e) => e.principal))).sort(),
    [entries],
  );
  const tools = useMemo(
    () => Array.from(new Set(entries.map((e) => toolFromAction(e.action)))).sort(),
    [entries],
  );

  const filtered = useMemo(() => {
    const cutoff = Date.now() - RANGE_DAYS[range] * 24 * 60 * 60 * 1000;
    return entries.filter((entry) => {
      if (actor !== ALL && entry.principal !== actor) return false;
      if (tool !== ALL && toolFromAction(entry.action) !== tool) return false;
      if (new Date(entry.at).getTime() < cutoff) return false;
      return true;
    });
  }, [entries, actor, tool, range]);

  return (
    <LedgerPanel
      entries={filtered}
      filters={
        <div className="flex flex-wrap gap-4">
          <select
            className={selectClasses}
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            aria-label="Filter by actor"
          >
            <option value={ALL}>All actors</option>
            {actors.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>

          <select
            className={selectClasses}
            value={tool}
            onChange={(e) => setTool(e.target.value)}
            aria-label="Filter by tool"
          >
            <option value={ALL}>All tools</option>
            {tools.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>

          <select
            className={selectClasses}
            value={range}
            onChange={(e) => setRange(e.target.value as DateRange)}
            aria-label="Filter by date range"
          >
            {DATE_RANGES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
      }
    />
  );
}
