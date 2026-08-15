/**
 * Types here intentionally mirror the enums and tables in the Python
 * backend's db/models.py (Population, TaskStatus, MeetingStatus, CiRun,
 * Crossing, ...), so `src/lib/api.ts` can fetch and cast into these types
 * with no further modeling work.
 */

export type Population = "client" | "ops" | "dev" | "lead" | "admin";

export type ChannelName = "telegram" | "discord" | "slack" | "email";

export type ChannelConnectionState = "live" | "reconnect_needed";

export interface ChannelStatus {
  channel: ChannelName;
  state: ChannelConnectionState;
  lastVerifiedMessageAt: string; // ISO timestamp
  messagesToday: number;
}

export type ProjectStatus = "done" | "in_review" | "in_progress";

export interface Project {
  id: string;
  name: string;
  phase: string;
  status: ProjectStatus;
  owner: string;
  note: string;
}

export interface Member {
  id: string;
  name: string;
  population: Population;
  channelBindingCount: number;
  joinedAt: string; // ISO date
}

export type ApprovalActionState = "pending";

export interface PendingApproval {
  id: string;
  name: string;
  claimedRole: Population;
  eligibleApprover: string;
}

export type ConferencingProvider = "google_meet" | "zoom";

export interface UpcomingMeeting {
  id: string;
  title: string;
  startsAt: string; // ISO timestamp
  organizer: string;
  provider: ConferencingProvider;
  attendeesConfirmed: number;
  attendeesTotal: number;
}

export type ReminderStage = "t_minus_24h" | "t_minus_60m" | "t_minus_10m";

export interface ScheduledReminder {
  id: string;
  meetingId: string;
  meetingTitle: string;
  stage: ReminderStage;
}

export interface PastMeeting {
  id: string;
  title: string;
  endedAt: string; // ISO timestamp
  organizer: string;
  provider: ConferencingProvider;
}

export type CiResult = "passed" | "failed" | "cancelled";

export interface CiRun {
  id: string;
  repo: string;
  workflowName: string;
  triggeredBy: string;
  result: CiResult;
  durationSeconds: number;
  finishedAt: string; // ISO timestamp
}

export interface LedgerEntry {
  id: string;
  principal: string;
  action: string;
  result: string;
  at: string; // ISO timestamp
}

/** One row of the per-role tool allowlist shown in the Allowlist panel. */
export interface AllowlistRow {
  tool: string;
  populations: Partial<Record<Population, boolean>>;
}

export interface StatStripItem {
  value: number | string;
  label: string;
}

export type ApiKeyStatus = "configured" | "missing";

export interface ChannelConfig {
  channel: ChannelName;
  apiKeyStatus: ApiKeyStatus;
}

export interface NotificationPreference {
  id: string;
  label: string;
  enabled: boolean;
}

export interface OrganizationInfo {
  name: string;
  adminContact: string;
  billingTier: string;
  /** Short code new members/clients type during onboarding to join this org. */
  joinCode: string;
}
