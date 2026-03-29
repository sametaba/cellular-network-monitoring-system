from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:admin@localhost:5432/cellular_monitoring"

    # App
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_TITLE: str = "AI Assisted Cellular Network Monitor"
    APP_VERSION: str = "0.1.0"

    # CORS — comma-separated list of allowed origins.
    # In development, "*" allows requests from the Vite dev server.
    # In production, set this to the exact frontend URL.
    CORS_ORIGINS: str = "*"


settings = Settings()
