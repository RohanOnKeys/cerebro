"""Unit tests for population-aware cortex prompt assembly."""

from datetime import UTC, datetime

from cerebro.cortex.prompts import (
    assemble_system_prompt,
    behavior_prompt,
    policy_prompt,
    time_context,
)
from cerebro.db.models import Population


def test_client_and_dev_system_prompts_differ():
    """CLIENT and DEV system prompts must not be identical."""
    client_prompt = assemble_system_prompt(Population.CLIENT)
    dev_prompt = assemble_system_prompt(Population.DEV)

    assert client_prompt
    assert dev_prompt
    assert client_prompt != dev_prompt


def test_behavior_and_policy_are_populated_for_client_and_dev():
    """Behavior and policy content must be present for CLIENT and DEV."""
    for population in (Population.CLIENT, Population.DEV):
        behavior = behavior_prompt(population)
        policy = policy_prompt(population)
        assert behavior.strip()
        assert policy.strip()
        assert "Cerebro" in behavior
        assert "Policy:" in policy
        assert f"population={population.value}" in policy


def test_client_policy_denies_enroll_principal():
    """CLIENT policy must deny enroll_principal."""
    policy = policy_prompt(Population.CLIENT)
    assert "enroll_principal" in policy
    assert "Denied" in policy


def test_dev_policy_allows_enroll_principal():
    """DEV policy must allow enroll_principal."""
    policy = policy_prompt(Population.DEV)
    assert "enroll_principal" in policy
    assert "Allowed tools" in policy
    assert "Denied tools" not in policy


def test_assemble_system_prompt_includes_behavior_and_policy():
    """Assembled system prompt contains both behavior and policy sections."""
    prompt = assemble_system_prompt(Population.CLIENT)
    assert behavior_prompt(Population.CLIENT) in prompt
    assert policy_prompt(Population.CLIENT) in prompt


def test_time_context_includes_the_given_moment():
    """The model needs the current time to resolve 'in 30 seconds', 'tomorrow
    at 3pm', etc. into an absolute ISO 8601 timestamp itself, instead of
    asking the user to compute one - see the 2026-08-15 set_reminder bug."""
    moment = datetime(2026, 8, 15, 17, 50, 0, tzinfo=UTC)

    context = time_context(now=moment)

    assert "2026-08-15T17:50:00Z" in context
    assert "never ask the user" in context.lower()


def test_assemble_system_prompt_includes_time_context():
    moment = datetime(2026, 8, 15, 17, 50, 0, tzinfo=UTC)

    prompt = assemble_system_prompt(Population.OPS, now=moment)

    assert "2026-08-15T17:50:00Z" in prompt


def test_time_context_defaults_to_real_time_when_omitted():
    before = datetime.now(UTC)
    context = time_context()
    after = datetime.now(UTC)

    # Just confirm it produced *some* timestamp in the current year, not that
    # it's frozen - a real clock read, bounded by the calls around it.
    assert str(before.year) in context or str(after.year) in context


def test_policy_allowed_tools_match_the_registry_for_every_population():
    """policy_prompt must never hardcode a tool list that drifts from TOOLS_FOR."""
    from cerebro.registry import TOOLS_FOR

    for population in Population:
        policy = policy_prompt(population)
        for tool in TOOLS_FOR[population]:
            assert tool.name in policy


def test_client_behavior_asks_for_input_in_layman_terms_too():
    """CLIENT tone must be symmetric: plain language for both output and asks."""
    behavior = behavior_prompt(Population.CLIENT)
    assert "no jargon" in behavior
    assert "ask" in behavior.lower()


def test_dev_behavior_asks_for_input_in_technical_terms_too():
    """DEV tone must be symmetric: technical language for both output and asks."""
    behavior = behavior_prompt(Population.DEV)
    assert "precise technical terms" in behavior
    assert "ask" in behavior.lower()


def test_assemble_system_prompt_includes_guardrails():
    """Every population's system prompt must include the guardrails block."""
    from cerebro.cortex.prompts import GUARDRAILS

    for population in Population:
        assert GUARDRAILS in assemble_system_prompt(population)
