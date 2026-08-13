interface SecondaryCapability {
  title: string;
  body: string;
}

const SECONDARY: SecondaryCapability[] = [
  {
    title: "Multichannel by default.",
    body: "One agent, four surfaces. Telegram, Discord, Slack, and Email all reach the same brain and speak with the same voice.",
  },
  {
    title: "Verified identity, always.",
    body: "Every sender proves who they are through a one time code before a single command runs.",
  },
  {
    title: "Notification routing by urgency.",
    body: "Quiet things land in the ledger, loud things escalate, and unanswered items follow up on their own.",
  },
  {
    title: "Meeting memory.",
    body: "Every decision is stored and retrievable by anyone with the right to see it.",
  },
  {
    title: "A central audit trail.",
    body: "Every event is logged: who asked, what ran, what it returned, when.",
  },
];

export function SecondaryCapabilities() {
  return (
    <section className="border-b border-cerebro-border py-20">
      <div className="mx-auto max-w-3xl px-6">
        <ul className="space-y-8">
          {SECONDARY.map((item) => (
            <li key={item.title}>
              <p className="font-display text-base font-semibold text-cerebro-ink">{item.title}</p>
              <p className="mt-1.5 text-sm leading-relaxed text-cerebro-muted">{item.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
