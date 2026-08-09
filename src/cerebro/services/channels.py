from dataclasses import dataclass
from enum import Enum


class ChannelType(str, Enum):
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    EMAIL = "email"
    WHATSAPP = "whatsapp"


@dataclass
class ChannelConfig:
    channel_type: ChannelType
    name: str
    avatar: str | None = None
    emoji: str | None = None
    color: str | None = None


# Global channel registry
_channels: dict[str, ChannelConfig] = {}


def install_slack(name: str, avatar: str | None = None, emoji: str = ":cerebro:") -> None:
    """Install Slack channel with branding."""
    config = ChannelConfig(
        channel_type=ChannelType.SLACK,
        name=name,
        avatar=avatar,
        emoji=emoji,
        color="#36C5F0",
    )
    _channels["slack"] = config


def install_discord(name: str, avatar: str | None = None, emoji: str = "🧠") -> None:
    """Install Discord channel with branding."""
    config = ChannelConfig(
        channel_type=ChannelType.DISCORD,
        name=name,
        avatar=avatar,
        emoji=emoji,
        color="#5865F2",
    )
    _channels["discord"] = config


def install_telegram(name: str, avatar: str | None = None, emoji: str = "🧠") -> None:
    """Install Telegram channel with branding."""
    config = ChannelConfig(
        channel_type=ChannelType.TELEGRAM,
        name=name,
        avatar=avatar,
        emoji=emoji,
        color="#0088cc",
    )
    _channels["telegram"] = config


def install_email(name: str, avatar: str | None = None, emoji: str = "📧") -> None:
    """Install Email channel with branding."""
    config = ChannelConfig(
        channel_type=ChannelType.EMAIL,
        name=name,
        avatar=avatar,
        emoji=emoji,
        color="#666666",
    )
    _channels["email"] = config


def install_whatsapp(name: str, avatar: str | None = None, emoji: str = "💬") -> None:
    """Install WhatsApp channel with branding."""
    config = ChannelConfig(
        channel_type=ChannelType.WHATSAPP,
        name=name,
        avatar=avatar,
        emoji=emoji,
        color="#25D366",
    )
    _channels["whatsapp"] = config


def update_branding(channel_type: str, name: str | None = None, avatar: str | None = None, emoji: str | None = None) -> None:
    """Update branding for an existing channel."""
    if channel_type not in _channels:
        raise ValueError(f"Channel {channel_type} not installed")

    config = _channels[channel_type]

    if name is not None:
        config.name = name
    if avatar is not None:
        config.avatar = avatar
    if emoji is not None:
        config.emoji = emoji


def get_channel_config(channel_type: str) -> ChannelConfig | None:
    """Get configuration for a channel."""
    return _channels.get(channel_type)


def list_channels() -> list[ChannelConfig]:
    """List all installed channels."""
    return list(_channels.values())
