from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    pilot_password: str = "change-me"
    data_dir: Path = Path("./data")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_mb: int = 25
    llm_provider: str = "deterministic"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-5-mini"
    openai_embedding_model: str | None = None
    agentic_workflow_enabled: bool = False
    agent_request_timeout_seconds: float = 20.0
    agent_workflow_timeout_seconds: float = 120.0
    canonical_language: str = "en"
    cross_project_reuse_enabled: bool = False
    external_web_enrichment_enabled: bool = False
    azure_search_endpoint: str | None = None
    azure_search_api_key: str | None = None
    azure_search_index_evidence: str = "erax-evidence-v1"
    azure_search_index_references: str = "erax-references-v1"
    azure_search_api_version: str = "2024-07-01"
    knowledge_blob_container_url: str | None = None
    azure_document_intelligence_endpoint: str | None = None
    azure_document_intelligence_api_key: str | None = None
    azure_document_intelligence_api_version: str = "2024-11-30"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
