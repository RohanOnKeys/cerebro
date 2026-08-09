"""OpenAI-compatible Featherless chat client."""

from __future__ import annotations

from typing import Any

import httpx


DEFAULT_FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"


class FeatherlessClient:
    """Thin client for Featherless OpenAI-compatible chat completions."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Create a client using explicit values or Settings/env defaults.

        Env fields: FEATHERLESS_API_KEY, FEATHERLESS_BASE_URL, MODEL_CORTEX.
        Secrets are never hardcoded; empty api_key is allowed for tests.
        """
        if api_key is None or base_url is None or model is None:
            from cerebro.config import settings

            if api_key is None:
                api_key = settings.featherless_api_key
            if base_url is None:
                base_url = settings.featherless_base_url or DEFAULT_FEATHERLESS_BASE_URL
            if model is None:
                model = settings.model_cortex

        self.api_key = api_key or ""
        self.base_url = (base_url or DEFAULT_FEATHERLESS_BASE_URL).rstrip("/")
        self.model = model or "gpt-4"
        self.timeout = timeout
        self._http = http_client or httpx.Client(timeout=timeout)
        self._owns_http = http_client is None

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> FeatherlessClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call chat completions and return the assistant message dict.

        Raises:
            httpx.HTTPStatusError: On non-success HTTP responses.
            ValueError: If the response has no choices/message.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        response = self._http.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Featherless response contained no choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("Featherless response missing assistant message")
        return message
