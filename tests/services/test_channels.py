import pytest

from cerebro.services.channels import (
    install_slack,
    install_discord,
    install_telegram,
    install_email,
    update_branding,
    get_channel_config,
    list_channels,
    _channels,
)


@pytest.fixture(autouse=True)
def cleanup():
    """Clear channels before each test."""
    _channels.clear()
    yield
    _channels.clear()


def test_install_slack():
    """Install Slack channel with branding."""
    install_slack("cerebro-slack")

    config = get_channel_config("slack")
    assert config is not None
    assert config.name == "cerebro-slack"
    assert config.emoji == ":cerebro:"
    assert config.color == "#36C5F0"


def test_install_discord():
    """Install Discord channel with branding."""
    install_discord("cerebro-discord", emoji="🧠")

    config = get_channel_config("discord")
    assert config is not None
    assert config.name == "cerebro-discord"
    assert config.emoji == "🧠"
    assert config.color == "#5865F2"


def test_install_telegram():
    """Install Telegram channel."""
    install_telegram("cerebro-telegram")

    config = get_channel_config("telegram")
    assert config is not None
    assert config.name == "cerebro-telegram"


def test_install_email():
    """Install Email channel."""
    install_email("cerebro-email")

    config = get_channel_config("email")
    assert config is not None
    assert config.name == "cerebro-email"


def test_update_branding():
    """Update branding for an installed channel."""
    install_slack("old-name")
    update_branding("slack", name="new-name", emoji="🆕")

    config = get_channel_config("slack")
    assert config.name == "new-name"
    assert config.emoji == "🆕"
    assert config.color == "#36C5F0"  # Unchanged


def test_update_branding_nonexistent_channel():
    """Update branding for non-existent channel raises error."""
    with pytest.raises(ValueError, match="Channel slack not installed"):
        update_branding("slack", name="cerebro")


def test_list_channels():
    """List all installed channels."""
    install_slack("slack-bot")
    install_discord("discord-bot")
    install_telegram("telegram-bot")

    channels = list_channels()
    assert len(channels) == 3
    assert any(c.name == "slack-bot" for c in channels)
    assert any(c.name == "discord-bot" for c in channels)
    assert any(c.name == "telegram-bot" for c in channels)


def test_three_channels_three_different_populations():
    """Three humans enrolled on three channels have different instances."""
    install_slack("slack-dev")
    install_discord("discord-ops")
    install_telegram("telegram-client")

    slack_config = get_channel_config("slack")
    discord_config = get_channel_config("discord")
    telegram_config = get_channel_config("telegram")

    assert slack_config.name == "slack-dev"
    assert discord_config.name == "discord-ops"
    assert telegram_config.name == "telegram-client"

    # Each has their own branding
    assert slack_config.emoji != discord_config.emoji
