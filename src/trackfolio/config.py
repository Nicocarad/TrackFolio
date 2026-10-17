"""Application settings, read from TRACKFOLIO_* environment variables or a local dotenv file."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "trackfolio.db"


class Settings(BaseSettings):
    """Runtime configuration; secrets come from the environment, never from the repo."""

    model_config = SettingsConfigDict(env_prefix="TRACKFOLIO_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{DATABASE_PATH.as_posix()}"
    openfigi_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENFIGI_API_KEY", "TRACKFOLIO_OPENFIGI_API_KEY"),
    )
    secure_cookies: bool = True  # only turn off for plain-HTTP development
    session_days: int = 14


def get_settings() -> Settings:
    """Load the settings; cheap, and not cached so tests can change the environment."""
    return Settings()
