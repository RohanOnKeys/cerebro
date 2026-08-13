export function ChannelRow() {
  return (
    <section className="border-b border-cerebro-border py-16">
      <div
        className="mx-auto flex max-w-3xl items-center justify-center gap-4 px-6 sm:gap-8"
        aria-label="Cerebro is reachable on Telegram and Email"
      >
        <ChannelNode label="Telegram" icon={TelegramIcon} />
        <Connector />
        <CerebroMark />
        <Connector />
        <ChannelNode label="Email" icon={EmailIcon} />
      </div>
    </section>
  );
}

function ChannelNode({
  label,
  icon: Icon,
}: {
  label: string;
  icon: (props: { className?: string }) => JSX.Element;
}) {
  return (
    <div className="flex flex-col items-center gap-3">
      <Icon className="h-7 w-7 text-cerebro-accent-lighter" />
      <span className="text-xs font-medium uppercase tracking-widest text-cerebro-muted">
        {label}
      </span>
    </div>
  );
}

function Connector() {
  return <div className="h-px w-12 bg-cerebro-accent-light sm:w-20" aria-hidden="true" />;
}

function CerebroMark() {
  return (
    <svg viewBox="0 0 40 40" className="h-9 w-9 text-cerebro-accent-lightest" aria-hidden="true">
      <circle cx="16" cy="20" r="10" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="24" cy="20" r="10" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <line x1="20" y1="9" x2="20" y2="31" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function TelegramIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M21.4 3.6 2.9 10.9c-1 .4-1 1.5.1 1.8l4.6 1.4 1.8 5.6c.2.7 1.1.9 1.6.3l2.5-2.8 4.7 3.5c.7.5 1.7.1 1.9-.7l3-16.4c.2-1-.8-1.7-1.7-1z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path
        d="M8.6 14.2 17 7.8 10.5 15l-.2 3.5-1.7-4.3Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function EmailIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <rect x="2.5" y="5" width="19" height="14" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="m3.5 6.5 8.5 6.5 8.5-6.5"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
