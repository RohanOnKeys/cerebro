export function formatTimestamp(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(iso));
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return remaining === 0 ? `${minutes}m` : `${minutes}m ${remaining}s`;
}

const REMINDER_STAGE_LABEL: Record<string, string> = {
  t_minus_24h: "24 hours before",
  t_minus_60m: "60 minutes before",
  t_minus_10m: "10 minutes before",
};

export function formatReminderStage(stage: string): string {
  return REMINDER_STAGE_LABEL[stage] ?? stage;
}

const POPULATION_LABEL: Record<string, string> = {
  client: "Client",
  ops: "Ops",
  dev: "Dev",
  lead: "Lead",
  admin: "Admin",
};

export function formatPopulation(population: string): string {
  return POPULATION_LABEL[population] ?? population;
}
