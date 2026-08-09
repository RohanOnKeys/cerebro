"""Unit tests for population-aware cortex prompt assembly."""

from cerebro.cortex.prompts import (
    assemble_system_prompt,
    behavior_prompt,
    policy_prompt,
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
