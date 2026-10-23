# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Define variables with their types and optional default values
    APP_NAME: str = "SnippetShare"
    database_url: str
    public_base_url: str
    debug: bool = False
    max_paste_bytes: int = 1_048_576

    # Automatically load values from a .env file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Single cached instance (alternative to dependency injection)
settings = Settings()