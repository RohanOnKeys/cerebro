export function Panel({
  id,
  title,
  children,
}: {
  id?: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-24 border-b border-cerebro-border py-10 first:pt-0 last:border-b-0"
    >
      <h2 className="text-metallic font-display text-xl font-semibold">{title}</h2>
      <div className="mt-2 h-px w-full bg-cerebro-border" aria-hidden="true" />
      <div className="mt-8">{children}</div>
    </section>
  );
}
