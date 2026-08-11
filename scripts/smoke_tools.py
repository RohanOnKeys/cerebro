"""Phase 0 gate: confirm at least one Featherless model returns real tool_calls.

Usage: python -m scripts.smoke_tools
Prints a PASS/FAIL line per candidate model and exits non-zero if none pass.
"""

from __future__ import annotations

import sys

from cerebro.cortex.featherless import FeatherlessClient

CANDIDATES: tuple[str, ...] = (
    "Qwen/Qwen3-32B",
    "Qwen/Qwen3.5-27B",
    "moonshotai/Kimi-K2-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",  # non-Qwen/Kimi control
)

_WHOAMI_TOOL = {
    "type": "function",
    "function": {
        "name": "whoami",
        "description": "Return the caller's identity.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}

_MESSAGES = [
    {
        "role": "user",
        "content": "Call the whoami tool right now to check who I am. Do not answer in text.",
    }
]


def probe(model: str) -> tuple[bool, str]:
    """Return (passed, detail) for one candidate model."""
    client = FeatherlessClient(model=model)
    try:
        message = client.chat(_MESSAGES, tools=[_WHOAMI_TOOL], tool_choice="required")
    except Exception as exc:  # noqa: BLE001 - smoke test reports any failure, doesn't crash the run
        return False, f"error: {type(exc).__name__}: {exc}"
    finally:
        client.close()

    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        name = (tool_calls[0].get("function") or {}).get("name", "?")
        return True, f"tool_calls=1 (called {name!r})"
    return False, f"no tool_calls; content={message.get('content')!r}"


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    for model in CANDIDATES:
        passed, detail = probe(model)
        results.append((model, passed, detail))
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {model} — {detail}")

    winners = [model for model, passed, _ in results if passed]
    print()
    if winners:
        print(f"Gate met: {len(winners)} model(s) returned tool_calls: {', '.join(winners)}")
        print(f"Set MODEL_CORTEX={winners[0]} in .env")
        return 0
    print("Gate NOT met: no candidate returned tool_calls. Consider TOOL_MODE=json fallback.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
