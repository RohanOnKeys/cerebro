interface SecondaryCapability {
  title: string;
  body: string;
}

const SECONDARY: SecondaryCapability[] = [
  {
    title: "Reach Us However You Already Talk.",
    body: "Message on Telegram or email, and it reaches the same team with the same answers, every time. No new app to learn.",
  },
  {
    title: "Verified, Every Time.",
    body: "Every message is confirmed to be from a real, known contact with a quick one-time code, so nothing runs on a guess.",
  },
  {
    title: "Nothing Urgent Gets Missed.",
    body: "Time-sensitive requests are flagged right away, and if nobody has responded in time, it's automatically escalated to make sure it gets seen.",
  },
  {
    title: "Meeting Memory.",
    body: "Ask what was decided in any meeting, any time, and get a straight answer instead of digging back through old messages.",
  },
  {
    title: "Nothing Falls Through the Cracks.",
    body: "Every request and every update is tracked from start to finish, so nothing gets lost or forgotten.",
  },
];

export function SecondaryCapabilities() {
  return (
    <section className="py-10 sm:py-12">
      <div className="mx-auto max-w-4xl px-6">
        {SECONDARY.map((item, index) => (
          <div
            key={item.title}
            className={`flex flex-wrap gap-8 border-t border-cerebro-border/60 py-6 ${
              index === SECONDARY.length - 1 ? "border-b" : ""
            }`}
          >
            <h4 className="w-full flex-shrink-0 font-landing text-base text-cerebro-ink sm:w-56">
              {item.title}
            </h4>
            <p className="min-w-[280px] flex-1 text-base leading-relaxed text-cerebro-muted">
              {item.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
