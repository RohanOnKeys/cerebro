/**
 * Admin/Read API client for the team dashboard.
 *
 * When NEXT_PUBLIC_CEREBRO_API_BASE_URL is unset (today), every getter returns
 * the typed mock data so the UI stays fully browsable. Once the Python
 * Admin/Read API exists, set the env var — these functions hit the API and
 * cast into src/lib/types.ts. Panel components do not change.
 */

import {
  activeProjects as mockProjects,
  allowlist as mockAllowlist,
  channelStatuses as mockChannels,
  ciRuns as mockCiRuns,
  ledgerEntries as mockLedger,
  members as mockMembers,
  pendingApprovals as mockApprovals,
  scheduledReminders as mockReminders,
  statStrip as mockStatStrip,
  upcomingMeetings as mockMeetings,
} from "@/lib/mock-data";
import type {
  AllowlistRow,
  ChannelStatus,
  CiRun,
  LedgerEntry,
  Member,
  PendingApproval,
  Project,
  ScheduledReminder,
  StatStripItem,
  UpcomingMeeting,
} from "@/lib/types";

function apiBase(): string {
  return (process.env.NEXT_PUBLIC_CEREBRO_API_BASE_URL ?? "").replace(/\/$/, "");
}

async function getJson<T>(path: string, fallback: T): Promise<T> {
  const base = apiBase();
  if (!base) {
    return fallback;
  }
  const response = await fetch(`${base}${path}`, {
    headers: { Accept: "application/json" },
    next: { revalidate: 30 },
  });
  if (!response.ok) {
    throw new Error(`Cerebro API ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function isLiveApiConfigured(): boolean {
  return apiBase().length > 0;
}

export async function getStatStrip(): Promise<StatStripItem[]> {
  return getJson("/admin/stats", mockStatStrip);
}

export async function getChannelStatuses(): Promise<ChannelStatus[]> {
  return getJson("/admin/channels", mockChannels);
}

export async function getActiveProjects(): Promise<Project[]> {
  return getJson("/admin/projects", mockProjects);
}

export async function getMembers(): Promise<Member[]> {
  return getJson("/admin/members", mockMembers);
}

export async function getPendingApprovals(): Promise<PendingApproval[]> {
  return getJson("/admin/approvals/pending", mockApprovals);
}

export async function getUpcomingMeetings(): Promise<UpcomingMeeting[]> {
  return getJson("/admin/meetings", mockMeetings);
}

export async function getScheduledReminders(): Promise<ScheduledReminder[]> {
  return getJson("/admin/reminders", mockReminders);
}

export async function getCiRuns(): Promise<CiRun[]> {
  return getJson("/admin/ci-runs", mockCiRuns);
}

export async function getLedgerEntries(): Promise<LedgerEntry[]> {
  return getJson("/admin/ledger", mockLedger);
}

export async function getAllowlist(): Promise<AllowlistRow[]> {
  return getJson("/admin/allowlist", mockAllowlist);
}
