from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    openai_api_key: str = ""
    chat_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    qdrant_url: str = "http://localhost:6333"
    collection: str = "documents"

    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 5

    # Comma-separated models that independently review extracted requirements.
    council_models: str = "gpt-4.1-mini,gpt-4.1-nano"
    # Minimum embedding cosine similarity for a generated requirement to match a ground-truth one.
    match_threshold: float = 0.7
    data_dir: str = "data"


settings = Settings()
