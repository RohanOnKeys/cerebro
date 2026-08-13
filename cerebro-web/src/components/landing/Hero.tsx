import { NeuralNetwork3D } from "@/components/landing/NeuralNetwork3D";

export function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-cerebro-border">
      <div className="pointer-events-none absolute inset-0 opacity-90">
        <NeuralNetwork3D />
      </div>

      <div className="relative mx-auto flex max-w-6xl flex-col items-center px-6 pb-28 pt-28 text-center sm:pt-36">
        <h1 className="text-metallic font-display text-6xl font-semibold leading-none tracking-tight sm:text-7xl">
          Cerebro
          <span className="text-cerebro-accent-lightest">: Agency Orchestration</span>
        </h1>

        <p className="mt-6 max-w-xl text-base text-cerebro-muted sm:text-lg">
          Walk out of your prison, work anywhere.
        </p>

        <a
          href="#talk-to-cerebro"
          className="mt-10 inline-flex items-center justify-center border border-cerebro-accent-light bg-cerebro-accent px-8 py-3 text-sm font-medium tracking-wide text-cerebro-ink transition-colors hover:bg-cerebro-accent-light"
        >
          Talk to Cerebro
        </a>
      </div>
    </section>
  );
}
