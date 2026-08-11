from cerebro.db.session import SessionLocal
from cerebro.ingress.dedupe import dedupe
from cerebro.ingress.principals import resolve_principal, touch_binding
from cerebro.ingress.enrollment import enroll_unknown_sender
from cerebro.ingress.commands import parse_command


async def on_message(sender: str, channel: str, text: str) -> str:
    """Main message handler.

    Order:
    1. Dedupe: check if message already processed
    2. Resolve/Enroll: find or create principal
    3. Touch: update binding timestamp
    4. Command: parse and validate command
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

        if not cmd:
            return "I didn't recognize that command. Try /WHOAMI or /HELP"

        reply = execute_command(cmd, principal, session)
        return reply

    finally:
        session.close()


def execute_command(cmd, principal, session) -> str:
    """Execute a parsed command and return reply."""
    from cerebro.ingress.commands import CommandVerb
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

        case _:
            return "Unknown command"
