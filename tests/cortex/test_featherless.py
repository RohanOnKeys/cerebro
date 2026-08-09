"""Unit tests for the Featherless HTTP client (mocked transport)."""

import httpx
import pytest

from cerebro.cortex.featherless import FeatherlessClient


def test_chat_posts_openai_compatible_payload():
    """Client posts to /chat/completions with Bearer auth and tools."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        body = request.read()
        assert b'"model":"test-model"' in body
        assert b'"tools"' in body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "hello",
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client = FeatherlessClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        http_client=http,
    )

    message = client.chat(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "whoami", "parameters": {}}}],
    )

    assert message["content"] == "hello"


def test_chat_raises_when_choices_missing():
    """Empty choices from Featherless raise ValueError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    transport = httpx.MockTransport(handler)
    client = FeatherlessClient(
        api_key="k",
        base_url="https://example.test/v1",
        model="m",
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(ValueError, match="no choices"):
        client.chat([{"role": "user", "content": "hi"}])
