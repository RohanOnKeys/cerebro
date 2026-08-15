export function Panel({
  id,
  title,
  action,
  children,
}: {
  id?: string;
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-24 border-b border-cerebro-border py-10 first:pt-0 last:border-b-0"
    >
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-metallic font-display text-xl font-semibold">{title}</h2>
        {action}
      </div>
      <div className="mt-2 h-px w-full bg-cerebro-border" aria-hidden="true" />
      <div className="mt-8">{children}</div>
    </section>
  );
}
