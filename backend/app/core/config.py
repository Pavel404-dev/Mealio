from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mealio Backend API"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+asyncpg://mealio_user:mealio_password@localhost:5432/mealio"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()