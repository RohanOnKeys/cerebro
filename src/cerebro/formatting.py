"""Lightweight markdown → HTML for Caspian channel replies.

Models naturally emit ChatGPT-style markdown (**bold**, `code`). Caspian
renders ``html=`` natively on Telegram/Slack/Discord/email, so we convert at
the send boundary instead of asking the model to invent channel-specific markup.
"""

from __future__ import annotations

import html
import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE = re.compile(r"`([^`]+)`")


def markdown_to_html(text: str) -> str:
    """Convert common markdown emphasis into simple HTML Caspian can render."""
    if not text:
        return ""
    escaped = html.escape(text)
    escaped = _BOLD.sub(r"<b>\1</b>", escaped)
    escaped = _ITALIC.sub(r"<i>\1</i>", escaped)
    escaped = _CODE.sub(r"<code>\1</code>", escaped)
    return escaped.replace("\n", "<br>\n")
