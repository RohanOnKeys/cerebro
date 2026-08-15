import type { Metadata } from "next";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { LedgerFilters } from "@/components/dashboard/LedgerFilters";
import { getDashboardData } from "@/lib/api";

export const metadata: Metadata = {
  title: "Ledger",
};

export const dynamic = "force-dynamic";

function isToday(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

function isWithinDays(iso: string, days: number): boolean {
  return new Date(iso).getTime() >= Date.now() - days * 24 * 60 * 60 * 1000;
}

export default async function LedgerPage() {
  const data = await getDashboardData();
  const entries = data.ledgerEntries;

  const stats = [
    { value: entries.filter((e) => isToday(e.at)).length, label: "Actions today" },
    { value: entries.filter((e) => isWithinDays(e.at, 7)).length, label: "Actions this week" },
    { value: new Set(entries.map((e) => e.principal)).size, label: "Unique actors" },
    {
      value: new Set(entries.map((e) => e.action.split("(")[0])).size,
      label: "Tools invoked",
    },
  ];

  return (
    <DashboardShell active="ledger" stats={stats}>
      <LedgerFilters entries={entries} />
    </DashboardShell>
  );
}
