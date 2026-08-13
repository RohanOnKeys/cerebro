const NAV_ITEMS = [
  { label: "Dashboard", href: "#top" },
  { label: "Channels", href: "#channels" },
  { label: "Projects", href: "#projects" },
  { label: "Members", href: "#members" },
  { label: "Meetings", href: "#meetings" },
  { label: "CI runs", href: "#ci-runs" },
  { label: "Ledger", href: "#ledger" },
  { label: "Allowlist", href: "#allowlist" },
] as const;

export function Sidebar() {
  return (
    <nav
      className="sticky top-0 h-screen w-56 shrink-0 overflow-y-auto border-r border-cerebro-border px-4 py-8"
      aria-label="Dashboard"
    >
      <ul className="space-y-1">
        {NAV_ITEMS.map((item, index) => (
          <li key={item.href}>
            <a
              href={item.href}
              className={`block px-4 py-2.5 text-sm transition-colors ${
                index === 0
                  ? "border-l-2 border-cerebro-accent-light bg-cerebro-bg-raised font-medium text-cerebro-ink"
                  : "border-l-2 border-transparent text-cerebro-muted hover:text-cerebro-ink"
              }`}
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
