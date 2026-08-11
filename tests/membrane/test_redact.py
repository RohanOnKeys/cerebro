"""Unit tests for field/digest redaction and the three-variant digest fan-out."""

from cerebro.membrane.redact import (
    build_digest_variants,
    redact_digest_text,
    redact_fields,
)


def test_redact_fields_drops_only_the_hidden_keys():
    fields = {"summary": "shipped", "stack_trace": "boom", "estimate": "3 days"}

    result = redact_fields(fields, ["stack_trace", "estimate"])

    assert result == {"summary": "shipped"}


def test_redact_digest_text_strips_labeled_lines_case_insensitively():
    text = "summary: all good\nStack_Trace: File x, line 1\nestimate: 2h"

    result = redact_digest_text(text, ["stack_trace", "estimate"])

    assert "summary: all good" in result
    assert "Stack_Trace" not in result
    assert "estimate: 2h" not in result


def test_redact_digest_text_with_no_hidden_fields_is_unchanged():
    text = "summary: all good\nstack_trace: File x"
    assert redact_digest_text(text, []) == text


def test_three_variants_differ_and_client_excludes_stack_trace_and_estimate():
    """Gate: client, team, and dev versions differ; no stack trace or estimate for client."""
    digest = "summary: shipped the release\nstack_trace: Traceback...\nestimate: 3 days\nrisk: none"

    variants = build_digest_variants(digest)

    assert set(variants) == {"client", "team", "dev"}
    assert variants["client"] != variants["team"] != variants["dev"]
    assert variants["client"] != variants["dev"]

    assert "stack_trace" not in variants["client"]
    assert "estimate" not in variants["client"]
    assert "summary" in variants["client"]

    # team sees more than client (estimate survives) but still no stack trace.
    assert "estimate: 3 days" in variants["team"]
    assert "stack_trace" not in variants["team"]

    # dev sees everything, unredacted.
    assert "stack_trace: Traceback..." in variants["dev"]
    assert "estimate: 3 days" in variants["dev"]
