import httpx

from cerebro.db.session import SessionLocal
from cerebro.ingress.dedupe import dedupe
from cerebro.ingress.principals import resolve_principal, touch_binding
from cerebro.ingress.enrollment import enroll_unknown_sender
from cerebro.ingress.commands import parse_command

_chat_client = None


def _get_chat_client():
    """Lazily construct and reuse one FeatherlessClient (owns a pooled httpx.Client)."""
    global _chat_client
    if _chat_client is None:
        from cerebro.cortex.featherless import FeatherlessClient

        _chat_client = FeatherlessClient()
    return _chat_client


async def on_message(sender: str, channel: str, text: str) -> str:
    """Main message handler.

    Order:
    1. Dedupe: check if message already processed
    2. Resolve/Enroll: find or create principal
    3. Touch: update binding timestamp
    4. Command: parse the fixed grammar; free text falls through to the cortex tool loop
    5. Reply: generate response
    """
    session = SessionLocal()

    try:
        message_id = f"{channel}:{sender}:{text[:20]}"

        if not dedupe(message_id):
            return "Message already processed"

        principal = resolve_principal(session, channel, sender)

        if not principal:
            org_id = "default_org"
            principal, binding = enroll_unknown_sender(
                session, org_id, channel, sender, f"conv_{message_id}"
            )
            return f"Welcome! You've been enrolled as {principal.population.value}"

        binding = touch_binding(session, principal.id, channel, sender)

        cmd = parse_command(text)

        if cmd:
            return execute_command(cmd, principal, session)

        return handle_free_text(text, principal, session, channel)

    finally:
        session.close()


def handle_free_text(text: str, principal, session, channel: str) -> str:
    """Route free text through the cortex tool loop, remembered via the message ledger."""
    from cerebro.cortex.loop import ToolRoundLimitExceeded, run_tool_loop
    from cerebro.services import messages as messages_service

    messages_service.record_message(
        session, principal=principal, channel=channel, role="user", content=text
    )
    history = messages_service.to_chat_messages(
        messages_service.recent_messages(session, principal_id=principal.id)
    )

    try:
        reply = run_tool_loop(
            _get_chat_client(),
            history,
            population=principal.population,
            principal=principal,
            session=session,
        )
        reply = reply.strip() if reply and reply.strip() else "Done."
    except ToolRoundLimitExceeded:
        reply = (
            "That needed more steps than I'm allowed to take at once — "
            "try breaking it into smaller requests."
        )
    except (httpx.HTTPError, ValueError):
        # LLM API boundary: a network hiccup or bad upstream response must not
        # take down the live channel loop the way an uncaught exception would.
        reply = "I couldn't reach the model to handle that — please try again in a moment."

    messages_service.record_message(
        session, principal=principal, channel=channel, role="assistant", content=reply
    )
    return reply


def execute_command(cmd, principal, session) -> str:
    """Execute a parsed command and return reply."""
    from cerebro.ingress.commands import CommandVerb
    from cerebro.membrane import crossings as crossings_service
    from cerebro.services import tasks as tasks_service

    match cmd.verb:
        case CommandVerb.WHOAMI:
            return f"You are {principal.id} ({principal.population.value})"

        case CommandVerb.ACK:
            if not cmd.args:
                return "ACK requires a task number"
            try:
                number = int(cmd.args[0])
            except ValueError:
                return f"'{cmd.args[0]}' is not a valid task number"
            task = tasks_service.ack_task(session, org_id=principal.org_id, number=number)
            if task is None:
                return f"Task {number} not found"
            return f"Task {number} acknowledged"

        case CommandVerb.BLOCKED:
            if not cmd.args:
                return "BLOCKED requires a task number"
            try:
                number = int(cmd.args[0])
            except ValueError:
                return f"'{cmd.args[0]}' is not a valid task number"
            reason = " ".join(cmd.args[1:]) or "no reason given"
            task = tasks_service.block_task(
                session, org_id=principal.org_id, number=number, principal=principal, reason=reason
            )
            if task is None:
                return f"Task {number} not found"
            return f"Task {number} marked as blocked and lead notified"

        case CommandVerb.CONFIRM:
            if not cmd.args:
                return "CONFIRM requires a nonce"
            nonce = cmd.args[0]
            return f"Confirmed action for {nonce}"

        case CommandVerb.DENY:
            if not cmd.args:
                return "DENY requires a nonce"
            nonce = cmd.args[0]
            return f"Denied action for {nonce}"

        case CommandVerb.ENROLL:
            return "Enrollment initiated"

        case CommandVerb.RERUN:
            if not cmd.args:
                return "RERUN requires a run ID"
            run_id = cmd.args[0]
            return f"Rerunning workflow {run_id}"

        case CommandVerb.DISPATCH:
            if len(cmd.args) < 1:
                return "DISPATCH requires workflow name"
            return f"Dispatching workflow {cmd.args[0]}"

        case CommandVerb.CANCEL:
            if not cmd.args:
                return "CANCEL requires a run ID"
            return f"Canceling run {cmd.args[0]}"

        case CommandVerb.AUDIT:
            if principal.population.value == "client":
                return "AUDIT is not available for your account"
            rows = crossings_service.list_crossings(session, org_id=principal.org_id)
            if not rows:
                return "No crossings recorded yet"
            lines = [
                f"{row.source_population}->{row.target_population} {row.action} ({row.status})"
                for row in rows[:10]
            ]
            return "Recent crossings:\n" + "\n".join(lines)

        case _:
            return "Unknown command"
