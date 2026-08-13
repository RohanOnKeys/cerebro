export function Footer() {
  return (
    <footer className="py-14">
      <div className="mx-auto flex max-w-5xl flex-col items-center gap-2 px-6 text-center">
        <p className="text-sm text-cerebro-ink">More to life, less to arrangements.</p>
        <a
          href="mailto:hello@cerebro.ai"
          className="text-sm text-cerebro-muted transition-colors hover:text-cerebro-accent-lighter"
        >
          hello@cerebro.ai
        </a>
      </div>
    </footer>
  );
}
