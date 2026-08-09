from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379"
    caspian_token: str = ""
    telegram_bot_token: str = ""
    slack_bot_token: str = ""
    discord_bot_token: str = ""
    github_app_id: str = ""
    github_private_key_b64: str = ""
    model_cortex: str = "gpt-4"
    featherless_api_key: str = ""
    featherless_base_url: str = "https://api.featherless.ai/v1"
    environment: str = "development"


settings = Settings()
