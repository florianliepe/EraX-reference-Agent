from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    pilot_password: str = "change-me"
    data_dir: Path = Path("./data")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_mb: int = 25
    llm_provider: str = "deterministic"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
