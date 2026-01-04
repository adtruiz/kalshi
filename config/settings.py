"""Application settings and configuration."""

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    """Environment types."""
    DEMO = "demo"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Configuration
    kalshi_api_key: str = Field(..., alias="KALSHI_API_KEY")
    kalshi_private_key_path: str = Field(
        default="./private_key.pem",
        alias="KALSHI_PRIVATE_KEY_PATH"
    )
    environment: Environment = Field(
        default=Environment.DEMO,
        alias="ENVIRONMENT"
    )

    # Rate Limits (Basic tier defaults)
    read_rate_limit: int = Field(default=20, alias="READ_RATE_LIMIT")
    write_rate_limit: int = Field(default=10, alias="WRITE_RATE_LIMIT")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def base_url(self) -> str:
        """Get the API base URL based on environment."""
        if self.environment == Environment.DEMO:
            return "https://demo-api.kalshi.co/trade-api/v2"
        return "https://api.elections.kalshi.com/trade-api/v2"

    @property
    def ws_url(self) -> str:
        """Get the WebSocket URL based on environment."""
        if self.environment == Environment.DEMO:
            return "wss://demo-api.kalshi.co/trade-api/ws/v2"
        return "wss://api.elections.kalshi.com/trade-api/ws/v2"

    @property
    def private_key_path(self) -> Path:
        """Get the private key path as a Path object."""
        return Path(self.kalshi_private_key_path)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
