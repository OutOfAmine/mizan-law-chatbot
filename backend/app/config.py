from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV, extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    # tried in order when the main model is overloaded (503) or rate-limited (429)
    gemini_fallbacks: str = "gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    rewrite_model: str = "gemini-3.1-flash-lite"
    # Embeddings run locally (fastembed / ONNX): no quota, no API call per question
    local_embed_model: str = "intfloat/multilingual-e5-large"
    embed_dim: int = 1024
    rerank_model: str = "jinaai/jina-reranker-v2-base-multilingual"
    rerank_pool: int = 30
    use_rerank: bool = False

    # Empty -> start the embedded local Postgres (pgserver) in ./pgdata
    database_url: str = ""

    # Comma-separated list of sites allowed to call the API (the widget's hosts)
    allowed_origins: str = "http://localhost:4200,http://localhost:8080"

    rate_limit: str = "8/minute"
    daily_limit: str = "100/day"
    max_question_chars: int = 500

    top_k: int = 12
    min_similarity: float = 0.78


settings = Settings()
