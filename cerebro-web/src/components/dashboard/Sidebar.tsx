import Link from "next/link";

export type NavKey =
  | "dashboard"
  | "projects"
  | "members"
  | "meetings"
  | "ci-runs"
  | "ledger"
  | "roles"
  | "settings";

const NAV_ITEMS: { key: NavKey; label: string; href: string }[] = [
  { key: "dashboard", label: "Dashboard", href: "/dashboard" },
  { key: "projects", label: "Projects", href: "/dashboard/projects" },
  { key: "members", label: "Members", href: "/dashboard/members" },
  { key: "meetings", label: "Meetings", href: "/dashboard/meetings" },
  { key: "ci-runs", label: "CI runs", href: "/dashboard/ci-runs" },
  { key: "ledger", label: "Ledger", href: "/dashboard/ledger" },
  { key: "roles", label: "Roles", href: "/dashboard/roles" },
  { key: "settings", label: "Settings", href: "/dashboard/settings" },
];

export function Sidebar({ active }: { active: NavKey }) {
  return (
    <nav
      className="sticky top-0 h-screen w-56 shrink-0 overflow-y-auto border-r border-cerebro-border px-4 py-8"
      aria-label="Dashboard"
    >
      <ul className="space-y-1">
        {NAV_ITEMS.map((item) => (
          <li key={item.key}>
            <Link
              href={item.href}
              aria-current={item.key === active ? "page" : undefined}
              className={`block px-4 py-2.5 text-sm transition-colors ${
                item.key === active
                  ? "border-l-2 border-cerebro-accent-light bg-cerebro-bg-raised font-medium text-cerebro-ink"
                  : "border-l-2 border-transparent text-cerebro-muted hover:text-cerebro-ink"
              }`}
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
