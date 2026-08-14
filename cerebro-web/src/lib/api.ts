import "server-only";
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
  ciRuns: CiRun[];
  ledgerEntries: LedgerEntry[];
  allowlist: AllowlistRow[];
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
    ciRuns,
    ledger,
    allowlist,
  ] = await Promise.all([
    getJson<Items<StatStripItem>>("/admin/stats"),
    getJson<Items<ChannelStatus>>("/admin/channels"),
    getJson<Items<Project>>("/admin/projects"),
    getJson<Items<Member>>("/admin/members"),
    getJson<Items<PendingApproval>>("/admin/approvals/pending"),
    getJson<Items<UpcomingMeeting>>("/admin/meetings"),
    getJson<Items<ScheduledReminder>>("/admin/reminders"),
    getJson<Items<CiRun>>("/admin/ci-runs"),
    getJson<Items<LedgerEntry>>("/admin/ledger"),
    getJson<Items<AllowlistRow>>("/admin/allowlist"),
  ]);

  const results = {
    stats,
    channels,
    projects,
    members,
    approvals,
    meetings,
    reminders,
    ciRuns,
    ledger,
    allowlist,
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
    ciRuns: ciRuns!.items,
    ledgerEntries: ledger!.items,
    allowlist: allowlist!.items,
  };
}
