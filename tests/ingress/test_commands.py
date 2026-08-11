import pytest

from cerebro.ingress.commands import parse_command, Command, CommandVerb


def test_parse_ack_with_arg():
    """Parse ACK with task ID argument."""
    cmd = parse_command("ACK 41")
    assert cmd is not None
    assert cmd.verb == CommandVerb.ACK
    assert cmd.args == ["41"]


def test_parse_confirm_with_arg():
    """Parse CONFIRM with nonce argument."""
    cmd = parse_command("CONFIRM 7qk3x2")
    assert cmd is not None
    assert cmd.verb == CommandVerb.CONFIRM
    assert cmd.args == ["7qk3x2"]


def test_parse_audit():
    """Parse AUDIT with no arguments."""
    cmd = parse_command("AUDIT")
    assert cmd is not None
    assert cmd.verb == CommandVerb.AUDIT
    assert cmd.args == []


def test_parse_case_insensitive():
    """Commands are case-insensitive."""
    cmd1 = parse_command("ack 41")
    cmd2 = parse_command("ACK 41")
    cmd3 = parse_command("AcK 41")

    assert cmd1.verb == cmd2.verb == cmd3.verb == CommandVerb.ACK


def test_parse_leading_slash():
    """Commands can have optional leading slash."""
    cmd1 = parse_command("ACK 41")
    cmd2 = parse_command("/ACK 41")

    assert cmd1.verb == cmd2.verb == CommandVerb.ACK
    assert cmd1.args == cmd2.args == ["41"]


def test_parse_whitespace_handling():
    """Commands handle extra whitespace."""
    cmd1 = parse_command("ACK 41")
    cmd2 = parse_command("ACK  41")
    cmd3 = parse_command("  ACK   41  ")

    assert cmd1.args == cmd2.args == cmd3.args == ["41"]


def test_parse_unknown_verb_returns_none():
    """Unknown verbs return None."""
    cmd = parse_command("INVALID 123")
    assert cmd is None


def test_parse_verb_only():
    """Parse verb without arguments."""
    cmd = parse_command("WHOAMI")
    assert cmd is not None
    assert cmd.verb == CommandVerb.WHOAMI
    assert cmd.args == []


def test_parse_multiple_args():
    """Parse command with multiple arguments."""
    cmd = parse_command("DISPATCH workflow_name branch_name")
    assert cmd is not None
    assert cmd.verb == CommandVerb.DISPATCH
    assert cmd.args == ["workflow_name", "branch_name"]


def test_parse_empty_string_returns_none():
    """Empty string returns None."""
    assert parse_command("") is None


def test_parse_whitespace_only_returns_none():
    """Whitespace-only string returns None."""
    assert parse_command("   ") is None


def test_parse_blocked_state_transition():
    """Parse BLOCKED state transition."""
    cmd = parse_command("BLOCKED 41")
    assert cmd is not None
    assert cmd.verb == CommandVerb.BLOCKED
    assert cmd.args == ["41"]


def test_parse_deny_command():
    """Parse DENY command."""
    cmd = parse_command("DENY 9kx2p1")
    assert cmd is not None
    assert cmd.verb == CommandVerb.DENY
    assert cmd.args == ["9kx2p1"]


def test_parse_slash_with_lowercase():
    """Parse /confirm with lowercase verb."""
    cmd = parse_command("/confirm 7qk3x2")
    assert cmd is not None
    assert cmd.verb == CommandVerb.CONFIRM
    assert cmd.args == ["7qk3x2"]


def test_parse_enroll_command():
    """Parse ENROLL command."""
    cmd = parse_command("ENROLL")
    assert cmd is not None
    assert cmd.verb == CommandVerb.ENROLL
    assert cmd.args == []


def test_parse_ci_commands():
    """Parse CI-related commands."""
    cmd1 = parse_command("RERUN 8842")
    cmd2 = parse_command("CANCEL abc123")

    assert cmd1.verb == CommandVerb.RERUN
    assert cmd1.args == ["8842"]
    assert cmd2.verb == CommandVerb.CANCEL
    assert cmd2.args == ["abc123"]
