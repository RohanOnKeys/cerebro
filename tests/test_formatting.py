"""Unit tests for markdown → HTML reply formatting."""

from cerebro.formatting import markdown_to_html


def test_bold_and_code_render_as_html():
    raw = "- **Principal ID**: `abc-123`\n- **Email**: robin@example.com"
    html = markdown_to_html(raw)
    assert "<b>Principal ID</b>" in html
    assert "<code>abc-123</code>" in html
    assert "**" not in html
    assert "`" not in html
    assert "<br>" in html


def test_plain_text_is_html_escaped():
    assert markdown_to_html("a < b & c") == "a &lt; b &amp; c"


def test_empty_input():
    assert markdown_to_html("") == ""
