import type { Project, ProjectStatus } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

const STATUS_LABEL: Record<ProjectStatus, string> = {
  done: "Done",
  in_review: "In review",
  in_progress: "In progress",
};

export function ActiveProjectsPanel({ projects }: { projects: Project[] }) {
  return (
    <Panel id="projects" title="Active projects">
      <div className="divide-y divide-cerebro-border border-y border-cerebro-border">
        {projects.map((project) => (
          <div key={project.id} className="grid grid-cols-1 gap-2 py-5 sm:grid-cols-[1.4fr_0.8fr_0.8fr_1fr_1.6fr] sm:items-center sm:gap-4">
            <span className="text-base font-medium text-cerebro-ink">{project.name}</span>
            <span className="text-sm text-cerebro-muted">{project.phase}</span>
            <span className="text-sm text-cerebro-accent-lightest">{STATUS_LABEL[project.status]}</span>
            <span className="text-sm text-cerebro-muted">{project.owner}</span>
            <span className="text-sm text-cerebro-muted">{project.note}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
