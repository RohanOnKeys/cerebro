import "server-only";
import type {
  AllowlistRow,
  ChannelConfig,
  ChannelStatus,
  CiRun,
  LedgerEntry,
  Member,
  NotificationPreference,
  OrganizationInfo,
  PastMeeting,
  PendingApproval,
  Project,
  ScheduledReminder,
  StatStripItem,
  UpcomingMeeting,
} from "@/lib/types";

/**
 * Server-only fetch layer for the Cerebro Admin/Read API.
 *
 * The `server-only` import above is load-bearing: it makes the build fail
 * loudly if anything in this file is ever imported from a Client Component.
 * That matters because CEREBRO_ADMIN_API_TOKEN must never reach the
 * browser — it's deliberately NOT prefixed with NEXT_PUBLIC_. The dashboard
 * page (src/app/dashboard/page.tsx) is a Server Component (no "use client"),
 * so these fetches run only during SSR; the token never ships in client JS.
 *
 * Every function here returns `null` on any failure (missing config,
 * network error, non-2xx response, bad shape) instead of throwing, so the
 * dashboard page can fall back to mock data and stay usable even if the
 * backend is down, unconfigured, or mid-deploy. See getDashboardData below.
 */

function apiBaseUrl(): string | null {
  const url = process.env.CEREBRO_API_BASE_URL;
  return url && url.trim().length > 0 ? url.replace(/\/+$/, "") : null;
}

function adminToken(): string | null {
  const token = process.env.CEREBRO_ADMIN_API_TOKEN;
  return token && token.trim().length > 0 ? token : null;
}

export function isApiConfigured(): boolean {
  return apiBaseUrl() !== null && adminToken() !== null;
}

async function getJson<T>(path: string): Promise<T | null> {
  const base = apiBaseUrl();
  const token = adminToken();
  if (!base || !token) return null;

  try {
    const res = await fetch(`${base}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      // Always fetch fresh at request time. This intentionally does NOT
      // use ISR/revalidate: doing so would make `next build` itself
      // attempt a live fetch to the backend, coupling every deploy to the
      // backend being reachable at build time. `dynamic = "force-dynamic"`
      // on the page (below) plus `cache: "no-store"` here keeps the build
      // and the backend fully decoupled — add caching back deliberately if
      // dashboard load starts to matter more than staleness.
      cache: "no-store",
    });
    if (!res.ok) {
      console.error(`Cerebro admin API ${path} returned ${res.status}`);
      return null;
    }
    return (await res.json()) as T;
  } catch (error) {
    console.error(`Cerebro admin API ${path} request failed`, error);
    return null;
  }
}

interface Items<T> {
  items: T[];
}

export type MutationResult<T> =
  | { kind: "mock" }
  | { kind: "ok"; data: T }
  | { kind: "error"; status: number };

/**
 * POSTs a mutation to the Admin API. Used by the Next.js Route Handlers
 * under src/app/api/** — never called from a Client Component directly
 * (same server-only guard/reasoning as getJson above). Those route
 * handlers are what a Client Component actually calls, over same-origin
 * fetch, so CEREBRO_ADMIN_API_TOKEN never has to leave the server.
 *
 * Distinguishes "not configured" (kind: "mock", so the caller can fall
 * back to a locally-simulated success and keep the dashboard interactive
 * in demo mode) from a real backend error (kind: "error"), unlike getJson
 * above which collapses every failure into mock data — a mutation that
 * silently no-ops on a real backend error should surface that, not pretend
 * to have succeeded.
 */
export async function postAdmin<T>(
  path: string,
  body?: unknown,
): Promise<MutationResult<T>> {
  const base = apiBaseUrl();
  const token = adminToken();
  if (!base || !token) return { kind: "mock" };

  try {
    const res = await fetch(`${base}${path}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
    if (!res.ok) {
      console.error(`Cerebro admin API POST ${path} returned ${res.status}`);
      return { kind: "error", status: res.status };
    }
    return { kind: "ok", data: (await res.json()) as T };
  } catch (error) {
    console.error(`Cerebro admin API POST ${path} request failed`, error);
    return { kind: "error", status: 502 };
  }
}

/**
 * Fetches every dashboard data source in parallel and returns a fully
 * populated result. `usingMockData` is true if the API isn't configured or
 * ANY fetch failed — the dashboard page uses that single flag to decide
 * whether to show the "sample data" banner, rather than tracking eight
 * separate fallback states.
 */
export async function getDashboardData(): Promise<{
  usingMockData: boolean;
  statStrip: StatStripItem[];
  channelStatuses: ChannelStatus[];
  activeProjects: Project[];
  members: Member[];
  pendingApprovals: PendingApproval[];
  upcomingMeetings: UpcomingMeeting[];
  scheduledReminders: ScheduledReminder[];
  pastMeetings: PastMeeting[];
  ciRuns: CiRun[];
  ledgerEntries: LedgerEntry[];
  allowlist: AllowlistRow[];
  channelConfig: ChannelConfig[];
  notificationPreferences: NotificationPreference[];
  organization: OrganizationInfo;
}> {
  const mock = await import("@/lib/mock-data");

  if (!isApiConfigured()) {
    return { usingMockData: true, ...mock };
  }

  const [
    stats,
    channels,
    projects,
    members,
    approvals,
    meetings,
    reminders,
    past,
    ciRuns,
    ledger,
    allowlist,
    channelConfig,
    notificationPreferences,
    organization,
  ] = await Promise.all([
    getJson<Items<StatStripItem>>("/admin/stats"),
    getJson<Items<ChannelStatus>>("/admin/channels"),
    getJson<Items<Project>>("/admin/projects"),
    getJson<Items<Member>>("/admin/members"),
    getJson<Items<PendingApproval>>("/admin/approvals/pending"),
    getJson<Items<UpcomingMeeting>>("/admin/meetings"),
    getJson<Items<ScheduledReminder>>("/admin/reminders"),
    getJson<Items<PastMeeting>>("/admin/meetings/past"),
    getJson<Items<CiRun>>("/admin/ci-runs"),
    getJson<Items<LedgerEntry>>("/admin/ledger"),
    getJson<Items<AllowlistRow>>("/admin/allowlist"),
    getJson<Items<ChannelConfig>>("/admin/channel-config"),
    getJson<Items<NotificationPreference>>("/admin/notification-preferences"),
    getJson<OrganizationInfo>("/admin/organization"),
  ]);

  const results = {
    stats,
    channels,
    projects,
    members,
    approvals,
    meetings,
    reminders,
    past,
    ciRuns,
    ledger,
    allowlist,
    channelConfig,
    notificationPreferences,
    organization,
  };
  const anyFailed = Object.values(results).some((r) => r === null);

  if (anyFailed) {
    // Partial data is worse than consistent mock data — a dashboard that's
    // half-real, half-placeholder is misleading. Fail the whole batch back
    // to mock data and let the banner say so.
    return { usingMockData: true, ...mock };
  }

  return {
    usingMockData: false,
    statStrip: stats!.items,
    channelStatuses: channels!.items,
    activeProjects: projects!.items,
    members: members!.items,
    pendingApprovals: approvals!.items,
    upcomingMeetings: meetings!.items,
    scheduledReminders: reminders!.items,
    pastMeetings: past!.items,
    ciRuns: ciRuns!.items,
    ledgerEntries: ledger!.items,
    allowlist: allowlist!.items,
    channelConfig: channelConfig!.items,
    notificationPreferences: notificationPreferences!.items,
    organization: organization!,
  };
}
