import type {
  AllowlistRow,
  CiRun,
  ChannelStatus,
  LedgerEntry,
  Member,
  PendingApproval,
  Project,
  ScheduledReminder,
  StatStripItem,
  UpcomingMeeting,
} from "@/lib/types";

/**
 * Placeholder data for the team dashboard.
 *
 * This file exists so the dashboard is fully browsable before the Cerebro
 * Admin/Read API (see the developer guide, section "Where the marketing and
 * the code disagree") is built. Every export here has the exact shape the
 * real API is expected to return (src/lib/types.ts) — replace the call
 * sites in src/app/dashboard/page.tsx with calls into src/lib/api.ts once
 * that endpoint exists. Nothing else in this app should need to change.
 */

export const statStrip: StatStripItem[] = [
  { value: 4, label: "Channels connected" },
  { value: 18, label: "Members" },
  { value: 3, label: "Pending approvals" },
  { value: 27, label: "CI runs this week" },
  { value: 6, label: "Meetings today" },
];

export const channelStatuses: ChannelStatus[] = [
  {
    channel: "telegram",
    state: "live",
    lastVerifiedMessageAt: "2026-08-14T09:12:00Z",
    messagesToday: 142,
  },
  {
    channel: "discord",
    state: "live",
    lastVerifiedMessageAt: "2026-08-14T09:04:00Z",
    messagesToday: 58,
  },
  {
    channel: "slack",
    state: "live",
    lastVerifiedMessageAt: "2026-08-14T08:57:00Z",
    messagesToday: 96,
  },
  {
    channel: "email",
    state: "reconnect_needed",
    lastVerifiedMessageAt: "2026-08-13T21:41:00Z",
    messagesToday: 4,
  },
];

export const activeProjects: Project[] = [
  {
    id: "proj-membrane-identity",
    name: "Membrane and identity",
    phase: "Phase 5",
    status: "done",
    owner: "Core team",
    note: "Crossing policy, redaction, and enrollment ask-flow shipped.",
  },
  {
    id: "proj-verification",
    name: "Verification challenges",
    phase: "Phase 6",
    status: "done",
    owner: "Core team",
    note: "Approvals ledger, CONFIRM/DENY executor, refusal paths.",
  },
  {
    id: "proj-ci",
    name: "CI GitHub App and triage",
    phase: "Phase 7",
    status: "done",
    owner: "Core team",
    note: "App auth, T0 reads, webhook triage, flake budget, T2 mutations.",
  },
  {
    id: "proj-phase-8-freeze",
    name: "Phase 8 freeze",
    phase: "Phase 8",
    status: "done",
    owner: "Core team",
    note: "WhatsApp cut, role approval gate, GCal/Zoom/Jira integrations.",
  },
  {
    id: "proj-admin-api",
    name: "Admin/Read API for dashboard",
    phase: "Phase 8+",
    status: "in_progress",
    owner: "Core team",
    note: "Dashboard UI ready; waiting on /admin/* read surface.",
  },
];

export const members: Member[] = [
  { id: "p-1", name: "Priya Shah", population: "lead", channelBindingCount: 3, joinedAt: "2026-02-11" },
  { id: "p-2", name: "Arjun Mehta", population: "dev", channelBindingCount: 2, joinedAt: "2026-02-14" },
  { id: "p-3", name: "Sara Ilić", population: "dev", channelBindingCount: 2, joinedAt: "2026-03-02" },
  { id: "p-4", name: "Tomás Rivera", population: "ops", channelBindingCount: 2, joinedAt: "2026-03-19" },
  { id: "p-5", name: "Wei Zhang", population: "admin", channelBindingCount: 4, joinedAt: "2026-01-30" },
  { id: "p-6", name: "Fatima Noor", population: "dev", channelBindingCount: 1, joinedAt: "2026-04-08" },
];

export const pendingApprovals: PendingApproval[] = [
  { id: "appr-1", name: "Daniel Osei", claimedRole: "dev", eligibleApprover: "Wei Zhang" },
  { id: "appr-2", name: "Lena Kowalski", claimedRole: "ops", eligibleApprover: "Wei Zhang" },
  { id: "appr-3", name: "Mateus Silva", claimedRole: "lead", eligibleApprover: "Wei Zhang" },
];

export const upcomingMeetings: UpcomingMeeting[] = [
  {
    id: "mtg-1",
    title: "Vendor contract review",
    startsAt: "2026-08-14T15:00:00Z",
    organizer: "Priya Shah",
    provider: "google_meet",
    attendeesConfirmed: 3,
    attendeesTotal: 5,
  },
  {
    id: "mtg-2",
    title: "Sprint planning",
    startsAt: "2026-08-14T18:30:00Z",
    organizer: "Arjun Mehta",
    provider: "zoom",
    attendeesConfirmed: 6,
    attendeesTotal: 6,
  },
  {
    id: "mtg-3",
    title: "Client onboarding call",
    startsAt: "2026-08-15T10:00:00Z",
    organizer: "Tomás Rivera",
    provider: "google_meet",
    attendeesConfirmed: 2,
    attendeesTotal: 4,
  },
];

export const scheduledReminders: ScheduledReminder[] = [
  { id: "rem-1", meetingId: "mtg-1", meetingTitle: "Vendor contract review", stage: "t_minus_24h" },
  { id: "rem-2", meetingId: "mtg-2", meetingTitle: "Sprint planning", stage: "t_minus_60m" },
  { id: "rem-3", meetingId: "mtg-3", meetingTitle: "Client onboarding call", stage: "t_minus_10m" },
];

export const ciRuns: CiRun[] = [
  {
    id: "run-1",
    repo: "cerebro",
    workflowName: "test",
    triggeredBy: "Arjun Mehta",
    result: "passed",
    durationSeconds: 192,
    finishedAt: "2026-08-14T08:40:00Z",
  },
  {
    id: "run-2",
    repo: "cerebro",
    workflowName: "deploy-staging",
    triggeredBy: "Sara Ilić",
    result: "failed",
    durationSeconds: 87,
    finishedAt: "2026-08-14T07:55:00Z",
  },
  {
    id: "run-3",
    repo: "cerebro-web",
    workflowName: "lint",
    triggeredBy: "Fatima Noor",
    result: "passed",
    durationSeconds: 41,
    finishedAt: "2026-08-14T07:20:00Z",
  },
  {
    id: "run-4",
    repo: "cerebro",
    workflowName: "deploy-staging",
    triggeredBy: "Wei Zhang",
    result: "cancelled",
    durationSeconds: 12,
    finishedAt: "2026-08-13T22:10:00Z",
  },
];

export const ledgerEntries: LedgerEntry[] = [
  {
    id: "led-1",
    principal: "Arjun Mehta",
    action: "dispatch_workflow(deploy-staging)",
    result: "run_id 18442 queued",
    at: "2026-08-14T08:36:00Z",
  },
  {
    id: "led-2",
    principal: "Cerebro (system)",
    action: "gap_chase(order-771, field:budget)",
    result: "asked once, awaiting reply",
    at: "2026-08-14T08:15:00Z",
  },
  {
    id: "led-3",
    principal: "Priya Shah",
    action: "schedule_meeting(Vendor contract review)",
    result: "meeting mtg-1 created",
    at: "2026-08-14T07:58:00Z",
  },
  {
    id: "led-4",
    principal: "Sara Ilić",
    action: "relay_to_population(client)",
    result: "redacted: stack_trace, estimate",
    at: "2026-08-14T07:42:00Z",
  },
  {
    id: "led-5",
    principal: "Wei Zhang",
    action: "cancel_run(run-4)",
    result: "cancel_requested",
    at: "2026-08-13T22:09:00Z",
  },
];

export const allowlist: AllowlistRow[] = [
  { tool: "whoami", populations: { client: true, ops: true, dev: true, lead: true, admin: true } },
  { tool: "open_order", populations: { client: true, ops: true, dev: true, lead: true, admin: true } },
  { tool: "schedule_meeting", populations: { client: true, ops: true, dev: true, lead: true, admin: true } },
  { tool: "cancel_meeting", populations: { client: true, ops: true, dev: true, lead: true, admin: true } },
  { tool: "relay_to_population", populations: { client: true, ops: true, dev: true, lead: true, admin: true } },
  { tool: "route_client_feedback", populations: { client: true, ops: true, dev: true, lead: true, admin: true } },
  { tool: "assign_task", populations: { ops: true, dev: true, lead: true, admin: true } },
  { tool: "enroll_principal", populations: { ops: true, dev: true, lead: true, admin: true } },
  { tool: "list_ci_runs", populations: { ops: true, dev: true, lead: true, admin: true } },
  { tool: "explain_ci_failure", populations: { ops: true, dev: true, lead: true, admin: true } },
  { tool: "rerun_workflow", populations: { ops: true, dev: true, lead: true, admin: true } },
  { tool: "dispatch_workflow", populations: { ops: true, dev: true, lead: true, admin: true } },
  { tool: "cancel_run", populations: { ops: true, dev: true, lead: true, admin: true } },
  { tool: "create_jira_ticket", populations: { ops: true, dev: true, lead: true, admin: true } },
  { tool: "jira_issue_status", populations: { ops: true, dev: true, lead: true, admin: true } },
];
