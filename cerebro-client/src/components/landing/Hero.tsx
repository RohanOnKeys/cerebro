import { BrainCanvas } from "@/components/landing/BrainCanvas";

export function Hero() {
  return (
    <section className="relative flex min-h-screen items-end overflow-hidden">
      <BrainCanvas />
      <div
        className="pointer-events-none absolute inset-0 z-[1] bg-[linear-gradient(90deg,rgba(28,30,34,0.82)_0%,rgba(28,30,34,0.5)_42%,rgba(28,30,34,0)_68%)]"
        aria-hidden="true"
      />

      <div className="relative z-[2] max-w-[660px] px-6 pb-16 sm:px-16 sm:pb-24">
        <div className="flex flex-col gap-1.5">
          <h1 className="text-metallic font-landing text-6xl leading-none tracking-tight sm:text-7xl md:text-8xl">
            Cerebro
          </h1>
          <span className="font-landing text-2xl text-cerebro-accent-lightest sm:text-3xl">
            Agency Orchestration
          </span>
        </div>
        <p className="mt-6 text-lg text-cerebro-muted sm:text-xl">
          Walk out of your prison, work anywhere.
        </p>
      </div>
    </section>
  );
}
