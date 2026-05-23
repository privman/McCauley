from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_url: str = "postgresql+asyncpg://mccauley:mccauley@localhost:5432/mccauley"
    session_secret: str = "dev-secret"

    anthropic_api_key: str = ""
    voyage_api_key: str = ""
    # Note: GCP credentials are read by google-cloud-{speech,texttospeech}
    # directly from the GOOGLE_APPLICATION_CREDENTIALS env var. We don't
    # mirror it into the Settings object because nothing in our code uses it.

    skills_dir: Path = Path("skills")
    seed_dir: Path = Path("ops/seed")

    sonnet_model: str = "claude-sonnet-4-6"
    haiku_model: str = "claude-haiku-4-5-20251001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
