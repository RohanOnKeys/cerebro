interface Capability {
  title: string;
  body: string;
}

const CAPABILITIES: Capability[] = [
  {
    title: "Ask, and It's Assigned.",
    body: "Tell Cerebro what you need in plain language, and it goes straight to the right person on the team — no forms, no waiting on a queue. Ask for an update any time and get a straight answer back in the same chat, instantly.",
  },
  {
    title: "Scheduling That Knows the Room.",
    body: "Cerebro checks everyone's real availability before it suggests a time. Once everyone agrees, the meeting is booked, the video link is ready, and each person gets notified on whatever app they actually use. No polls, no double-booking, no back and forth.",
  },
  {
    title: "Always in the Loop.",
    body: "Ask what's being worked on, what's done, or what's next, and get a plain answer immediately — no chasing anyone down. Every question reaches a real person on the team and gets tracked until it's answered.",
  },
];

export function CoreCapabilities() {
  return (
    <section className="py-16 sm:py-20" id="talk-to-cerebro">
      <div className="mx-auto max-w-6xl px-6">
        {CAPABILITIES.map((capability, index) => (
          <div
            key={capability.title}
            className={`grid grid-cols-1 gap-6 border-t border-cerebro-border py-16 sm:grid-cols-[360px_1fr] sm:gap-14 ${
              index === CAPABILITIES.length - 1 ? "border-b" : ""
            }`}
          >
            <h3 className="font-landing text-2xl leading-snug text-cerebro-ink sm:text-3xl">
              {capability.title}
            </h3>
            <p className="max-w-3xl text-base leading-relaxed text-cerebro-muted sm:text-lg">
              {capability.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
