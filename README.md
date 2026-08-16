# CEREBRO

### The company second brain.

![Cerebro](assets/cerebro-hero.gif)

Cerebro is an office workspace assistant, a project manager, and a CI monitor, running as one identity across every channel your company already lives in. It does not just answer questions. It opens the ticket, finds the right person for the work, books the meeting on a real calendar, and chases the reply that never came.

You do not open a new app. You do not learn a new interface. You message Cerebro on Telegram, Discord, Slack, or Email, and the office answers back.

**walk out of your prison, work anywhere**

**because the only time one should be enclosed in a box, is when they are dead**

![Anywhere](assets/anywhere.jpg)

---

## Live

**Team dashboard:** https://cerebro-teams.vercel.app

**Client site:** https://cerebro-client.vercel.app

**Source:** https://github.com/RohanOnKeys/cerebro

### Talk to it

- **Discord:** https://discord.gg/C4Kmnzkwu
- **Slack:** https://join.slack.com/t/secondbrain-pnl3918/shared_invite/zt-46iwnm6dg-gMjDMzDWVQ2QyZEy488ZRQ
- **Email:** cerebro-1d74f5@agents.trycaspianai.com
- **Telegram:** @cerebro_operations_bot

---

## What's new

Cerebro used to answer questions. Now it closes the loop on its own, and the newest work is what actually makes that true.

**A ticket raises itself.** The moment a client opens a request on any channel, a background pass reads the order, works out which team it belongs to, splits it into real tasks, assigns each one to somebody who can actually do it, and opens a Jira ticket with the original ask as its description. Nobody has to remember to write the ticket. It already exists by the time a human looks up.

**Assignment that reasons about capacity, not just availability.** A task is offered to a team designation first, then filtered to whoever has the required skills, then filtered again to whoever is under their work in progress cap, and finally handed to whichever remaining person is carrying the least right now. The same chain runs whether the order came in on Telegram at nine in the morning or Discord at midnight.

![Work anywhere](assets/dark-laptop.jpg)

**Meetings that produce a real, working link.** Ask for a call with a client and Cerebro checks the calendar, proposes the earliest slot that actually works, and, if you want a Zoom room, creates one for real through the Zoom API and hands back a link a person can click. Nothing about scheduling depends on Google. The meeting itself lives in Cerebro's own calendar, so a slot check never depends on an external account being configured correctly.

**Reminders and deadlines that do not need a calendar app.** A team reminder or a client-requested deadline is a row Cerebro owns and fires on its own clock. Ask to be reminded, or ask for a deadline to be set, and it goes off exactly once, on time, on whichever channel you actually read.

**Jira, live, both directions.** Cerebro does not only create tickets. Ask it the status of one by key and it reads straight from Jira and tells you where things stand, in the same sentence you asked in.

---

## How it works

Every tool, table, and background job Cerebro actually runs — channel intake, identity, the tool-calling loop, tier gating, services, Postgres, the scheduler, CI, and the two dashboards — is documented in **[`architecture.md`](architecture.md)**.

---

## Tools available to the agent

Every capability above is a plain callable in `registry.py`, gated by population (client, ops, dev, lead, admin) and, for anything that changes something outside Cerebro, by a confirm before run tier.

- **Orders and tasks:** `open_order`, `update_order_fields`, `order_status`, `list_orders`, `decompose_order`, `assign_task`, `ack_task`, `block_task`, `list_tasks`
- **Scheduling:** `schedule_meeting`, `rsvp_meeting`, `list_meetings`, `meeting_status`, `cancel_meeting`
- **Jira:** `create_jira_ticket`, `jira_issue_status`
- **Summaries:** `request_summary`, `submit_summary`
- **CI:** `list_ci_runs`, `explain_ci_failure`, `rerun_workflow` (confirm), `dispatch_workflow` (confirm), `cancel_run` (confirm)
- **Cross team routing:** `relay_to_population` for a redacted digest across a population boundary, `route_client_feedback` for a client's message about a specific task, both written to an audited crossings ledger
- **Team broadcast:** `post_incident_update`, for telling an entire team something at once, the same tool behind "tell the backend team the staging db is down"

---

## Frameworks and tools

**Caspian SDK** is the channel layer, one `on_message` handler for Telegram, Discord, Slack, and Email alike.

**FastAPI plus a Featherless hosted model** is the core, routing free text to a tool call and pulling the arguments straight out of the sentence.

**Postgres**, one database, holds every ledger: principals, orders, tasks, meetings, reminders, CI runs, and the audited crossings between teams.

![Ledgers](assets/ledger-stream.jpg)

**Jira Cloud's REST API** is where tickets actually live, raised automatically and readable on demand.

**Zoom's Server to Server OAuth API** mints the real conferencing links behind a scheduled meeting.

**GitHub's REST API and webhooks** handle a dispatched workflow going out and its result coming back.

![CI](assets/ci-wake-up.jpg)

**The dashboard** is its own server, reaching the core through an admin, read only API over HTTPS.

---

## Why it helps the office

The cost of coordination is never the meeting. It is everything around the meeting: finding the slot, writing the ticket nobody got to, working out who should actually own the work, chasing the reply, remembering what was decided, checking whether the thing shipped. Cerebro absorbs that layer and hands back the part of the day you actually got hired for.

It works because it meets people where they already are. There is no adoption curve for a system that arrives as a message from a contact you already have.
