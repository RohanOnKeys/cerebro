import re
from dataclasses import dataclass
from enum import Enum


class CommandVerb(str, Enum):
    ACK = "ACK"
    BLOCKED = "BLOCKED"
    CONFIRM = "CONFIRM"
    DENY = "DENY"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    WHOAMI = "WHOAMI"
    ENROLL = "ENROLL"
    RERUN = "RERUN"
    DISPATCH = "DISPATCH"
    CANCEL = "CANCEL"
    AUDIT = "AUDIT"


@dataclass
class Command:
    verb: CommandVerb
    args: list[str]

    def __repr__(self):
        return f"Command({self.verb.value}, {self.args})"


def parse_command(text: str) -> Command | None:
    """Parse a command from text.

    Grammar:
    - Optional leading slash
    - Verb (case-insensitive, must be a known verb)
    - Optional arguments (space-separated)
    - Flexible whitespace handling

    Returns Command if valid, None if not a command.
    """
    text = text.strip()

    if not text:
        return None

    if text.startswith("/"):
        text = text[1:].strip()

    parts = text.split()
    if not parts:
        return None

    verb_str = parts[0].upper()

    try:
        verb = CommandVerb[verb_str]
    except KeyError:
        return None

    args = parts[1:]

    return Command(verb=verb, args=args)
