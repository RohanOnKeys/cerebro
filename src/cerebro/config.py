from typing import Literal

from pydantic import ConfigDict, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6380"
    caspian_api_key: str = ""
    caspian_base_url: str = "https://api.trycaspianai.com"
    discord_invite_url: str = ""
    slack_invite_url: str = ""
    email_address: str = ""
    telegram_handle: str = ""
    github_app_id: str = ""
    github_private_key_b64: str = ""
    github_installation_id: str = ""
    model_cortex: str = "gpt-4"
    featherless_api_key: str = ""
    featherless_base_url: str = "https://api.featherless.ai/v1"
    tool_mode: Literal["native", "json"] = "native"
    environment: str = "development"
    nudge_time_scale: float = 1.0

    @field_validator("tool_mode", mode="before")
    @classmethod
    def normalize_tool_mode(cls, value: object) -> object:
        """Normalize TOOL_MODE to a supported literal."""
        if isinstance(value, str):
            return value.strip().lower()
        return value


settings = Settings()
