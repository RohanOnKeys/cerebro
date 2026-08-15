import type { Metadata } from "next";
import { ActiveProjectsPanel } from "@/components/dashboard/ActiveProjectsPanel";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { ProjectTimelinePanel } from "@/components/dashboard/ProjectTimelinePanel";
import { getDashboardData } from "@/lib/api";

export const metadata: Metadata = {
  title: "Projects",
};

export const dynamic = "force-dynamic";

export default async function ProjectsPage() {
  const data = await getDashboardData();
  const projects = data.activeProjects;

  const stats = [
    { value: projects.length, label: "Total projects" },
    { value: projects.filter((p) => p.status === "in_progress").length, label: "In progress" },
    { value: projects.filter((p) => p.status === "in_review").length, label: "In review" },
    { value: projects.filter((p) => p.status === "done").length, label: "Done this quarter" },
  ];

  return (
    <DashboardShell active="projects" stats={stats}>
      <ActiveProjectsPanel projects={projects} />
      <ProjectTimelinePanel projects={projects} />
    </DashboardShell>
  );
}
