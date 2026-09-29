"""
config.py — Central configuration loader.

Reads all settings from environment variables (loaded from .env).
Every other module imports from here — no os.getenv() calls scattered
across the codebase.
"""

import os
from dotenv import load_dotenv

# Load the .env file into os.environ before anything else reads it.
load_dotenv()


class Config:
    """
    Base configuration shared by all environments.

    Using a class (instead of a plain dict) means:
    - Attributes are type-hinted and discoverable
    - You can subclass for different environments (Dev / Prod)
    - Flask's app.config.from_object() works natively with it
    """

    # ------------------------------------------------------------------
    # Flask core
    # ------------------------------------------------------------------
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-fallback-secret-key")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # ------------------------------------------------------------------
    # Database
    # SQLAlchemy reads DATABASE_URL to know which engine to use.
    # sqlite:///supportflow.db  → local SQLite file
    # postgresql://...          → PostgreSQL (zero code changes needed)
    # ------------------------------------------------------------------
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL", "sqlite:///supportflow.db"
    )
    # Disable modification tracking — it adds overhead and we don't need it
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # ------------------------------------------------------------------
    # OpenRouter / AI
    # ------------------------------------------------------------------
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv(
        "OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
    )
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # ------------------------------------------------------------------
    # Ticket validation limits
    # ------------------------------------------------------------------
    MAX_MESSAGE_LENGTH: int = 2000   # characters
    MIN_MESSAGE_LENGTH: int = 5      # characters

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------
    RATELIMIT_DEFAULT: str = os.getenv("RATE_LIMIT", "10 per minute")
    RATELIMIT_STORAGE_URI: str = "memory://"   # Use Redis URI in production


class DevelopmentConfig(Config):
    """Development-specific overrides."""
    DEBUG = True


class ProductionConfig(Config):
    """Production-specific overrides."""
    DEBUG = False


class TestingConfig(Config):
    """
    Testing-specific overrides.
    Uses an in-memory SQLite database so tests never touch the real DB.
    """
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Disable rate limiting during tests
    RATELIMIT_ENABLED = False


# Map string names to config classes.
# Usage: app.config.from_object(config_map["development"])
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config() -> Config:
    """
    Return the correct config class based on FLASK_ENV.
    Defaults to development if not set.
    """
    env = os.getenv("FLASK_ENV", "development").lower()
    return config_map.get(env, DevelopmentConfig)
