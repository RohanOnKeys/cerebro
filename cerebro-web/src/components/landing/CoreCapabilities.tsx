interface Capability {
  title: string;
  body: string;
}

const CAPABILITIES: Capability[] = [
  {
    title: "Jira, from the chat you're already in.",
    body: "Cerebro opens tickets the moment work is identified, filing them straight into the right project with the right labels and issue type, no context switch required. Ask for a status update on any ticket by its key and get the current state and summary back instantly, so the backlog stays accurate without anyone having to open Jira to check it.",
  },
  {
    title: "Scheduling that knows the room.",
    body: "Cerebro reads real Google Calendar availability across every attendee before it proposes a single time. Once a slot is confirmed, it creates the event, generates the Meet link, and notifies each attendee on the channel that person actually reads. No polls in a thread nobody opens, no double bookings, no back and forth.",
  },
  {
    title: "CI as a conversation.",
    body: "Trigger a GitHub Actions workflow, watch it run, and get told how it ended, all from the same chat window you were already complaining in. If a run needs to be stopped, Cerebro cancels it on request. Every trigger, result, and cancellation is tied back to the verified person who asked for it.",
  },
];

export function CoreCapabilities() {
  return (
    <section className="border-b border-cerebro-border py-24 sm:py-32" id="talk-to-cerebro">
      <div className="mx-auto max-w-5xl px-6">
        <h2 className="font-display text-sm font-semibold uppercase tracking-widest text-cerebro-accent-lighter">
          Core capabilities
        </h2>

        <div className="mt-10">
          {CAPABILITIES.map((capability, index) => (
            <div
              key={capability.title}
              className={`grid grid-cols-1 gap-6 py-14 sm:grid-cols-[1fr_1.6fr] sm:gap-16 ${
                index === 0 ? "" : "border-t border-cerebro-border"
              }`}
            >
              <h3 className="font-display text-2xl font-semibold leading-snug text-cerebro-ink sm:text-3xl">
                {capability.title}
              </h3>
              <p className="text-base leading-relaxed text-cerebro-muted sm:text-lg">
                {capability.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
