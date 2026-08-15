import type { Project, ProjectStatus } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";
import { ViewAllLink } from "@/components/dashboard/ViewAllLink";

const STATUS_LABEL: Record<ProjectStatus, string> = {
  done: "Done",
  in_review: "In review",
  in_progress: "In progress",
};

const STATUS_COLOR: Record<ProjectStatus, string> = {
  done: "text-cerebro-success",
  in_review: "text-cerebro-accent-lightest",
  in_progress: "text-cerebro-warning",
};

export function ActiveProjectsPanel({
  projects,
  limit,
  viewAllHref,
}: {
  projects: Project[];
  limit?: number;
  viewAllHref?: string;
}) {
  const rows = limit ? projects.slice(0, limit) : projects;

  return (
    <Panel
      id="projects"
      title="Active projects"
      action={viewAllHref ? <ViewAllLink href={viewAllHref} /> : undefined}
    >
      <div className="divide-y divide-cerebro-border border-y border-cerebro-border">
        {rows.map((project) => (
          <div key={project.id} className="grid grid-cols-1 gap-2 py-5 sm:grid-cols-[1.4fr_0.8fr_0.8fr_1fr_1.6fr] sm:items-center sm:gap-4">
            <span className="text-base font-medium text-cerebro-ink">{project.name}</span>
            <span className="text-sm text-cerebro-muted">{project.phase}</span>
            <span className={`text-sm ${STATUS_COLOR[project.status]}`}>{STATUS_LABEL[project.status]}</span>
            <span className="text-sm text-cerebro-muted">{project.owner}</span>
            <span className="text-sm text-cerebro-muted">{project.note}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
