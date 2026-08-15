import type { Project, ProjectStatus } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

const STATUS_LABEL: Record<ProjectStatus, string> = {
  done: "Done",
  in_review: "In review",
  in_progress: "In progress",
};

const DOT_COLOR: Record<ProjectStatus, string> = {
  done: "bg-cerebro-success border-cerebro-success",
  in_review: "bg-cerebro-accent-lightest border-cerebro-accent-lightest",
  in_progress: "border-cerebro-warning bg-transparent",
};

// Reuses the existing project roster (in phase order) as a delivery
// timeline, rather than one project's internal phase history — the mock
// data models projects, not per-project phase logs, so this gets the same
// stepped-progress visual out of data we already have.
export function ProjectTimelinePanel({ projects }: { projects: Project[] }) {
  return (
    <Panel title="Delivery timeline">
      <div className="flex items-start">
        {projects.map((project, index) => (
          <div key={project.id} className="flex flex-1 items-center last:flex-none">
            <div className="flex min-w-[140px] flex-col items-center gap-2.5 text-center">
              <div className={`h-3.5 w-3.5 rounded-full border ${DOT_COLOR[project.status]}`} aria-hidden="true" />
              <span className="text-sm font-medium text-cerebro-ink">{project.phase}</span>
              <span className="text-xs text-cerebro-muted">{project.name}</span>
              <span className="text-xs text-cerebro-muted">{STATUS_LABEL[project.status]}</span>
            </div>
            {index < projects.length - 1 && (
              <div className="mb-14 h-px flex-1 bg-cerebro-border" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
