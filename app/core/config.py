from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    wiki_base_url: str = "https://battlenations.miraheze.org/w/api.php"
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 3600
    api_title: str = "Battle Nations Wiki API"
    log_level: str = "INFO"


settings = Settings()