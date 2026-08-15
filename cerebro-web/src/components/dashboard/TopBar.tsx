import Image from "next/image";

export function TopBar() {
  return (
    <header className="flex h-20 items-center gap-8 border-b border-cerebro-border px-8">
      <span className="flex items-center gap-2.5">
        <Image src="/cerebro-brain.png" alt="" width={24} height={24} className="h-6 w-6 object-contain" />
        <span className="text-metallic font-display text-xl font-semibold tracking-tight">
          Cerebro
        </span>
      </span>

      <div className="flex-1">
        <label className="sr-only" htmlFor="global-search">
          Search
        </label>
        <input
          id="global-search"
          type="search"
          placeholder="Search members, projects, runs, ledger entries…"
          className="w-full max-w-xl border border-cerebro-border bg-cerebro-bg-raised px-4 py-2.5 text-sm text-cerebro-ink placeholder:text-cerebro-muted focus:border-cerebro-accent-light focus:outline-none"
        />
      </div>

      <div className="flex items-center gap-3">
        <div className="text-right">
          <p className="text-sm font-medium text-cerebro-ink">Team dashboard</p>
          <p className="text-xs text-cerebro-muted">Admin</p>
        </div>
        <div
          className="flex h-9 w-9 items-center justify-center border border-cerebro-border bg-cerebro-bg-raised"
          aria-hidden="true"
        >
          <Image src="/cerebro-brain.png" alt="" width={20} height={20} className="h-5 w-5 object-contain" />
        </div>
      </div>
    </header>
  );
}
