from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_url: str = "postgresql+asyncpg://mccauley:mccauley@localhost:5432/mccauley"
    session_secret: str = "dev-secret"

    anthropic_api_key: str = ""
    voyage_api_key: str = ""
    google_application_credentials: str = ""

    skills_dir: Path = Path("skills")
    seed_dir: Path = Path("ops/seed")

    sonnet_model: str = "claude-sonnet-4-6"
    haiku_model: str = "claude-haiku-4-5-20251001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
