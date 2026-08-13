import type { StatStripItem } from "@/lib/types";

export function StatStrip({ items }: { items: StatStripItem[] }) {
  return (
    <div className="border-b border-cerebro-border px-8 py-10">
      <dl className="grid grid-cols-2 gap-8 sm:grid-cols-3 lg:grid-cols-5">
        {items.map((item) => (
          <div key={item.label}>
            <dd className="font-display text-4xl font-semibold text-cerebro-accent-lightest sm:text-5xl">
              {item.value}
            </dd>
            <dt className="mt-2 text-sm text-cerebro-muted">{item.label}</dt>
          </div>
        ))}
      </dl>
    </div>
  );
}
