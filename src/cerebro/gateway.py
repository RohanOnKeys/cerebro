"""Live gateway: bridges real caspian-sdk channel connections to on_message."""

from __future__ import annotations

from caspian_sdk import CommClient
from caspian_sdk.client import Message

from cerebro.clock.scheduler import Scheduler
from cerebro.db.session import SessionLocal
from cerebro.main import on_message
from cerebro.services.gap_chase import register_gap_chase_job


async def handle_message(message: Message) -> None:
    """Bridge one inbound caspian message into main.on_message and reply."""
    sender = (message.sender or {}).get("address", "unknown")
    reply_text = await on_message(sender, message.channel, message.text or "")
    message.reply(reply_text)


def run_gateway() -> None:
    """Start the background scheduler, then block on the live message loop."""
    client = CommClient()
    client.on_message(handle_message)

    scheduler = Scheduler()
    register_gap_chase_job(scheduler, SessionLocal)
    scheduler.start()

    client.listen()


if __name__ == "__main__":
    run_gateway()
