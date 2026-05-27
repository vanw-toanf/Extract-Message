from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
import os


load_dotenv()


class Settings(BaseModel):
    admin_db_path: Path = Path(
        os.getenv("ADMIN_DB_PATH", "vietnam_admin_db/vietnam_administrative.json")
    )
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    llm_base_url: str = os.getenv(
        "LLM_BASE_URL", os.getenv("LLM_LINK", "http://localhost:11434")
    )
    llm_model: str = os.getenv("LLM_MODEL", "qwen2.5:7b")
    llm_api_key: str = os.getenv("LLM_API_KEY", "ollama")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    enable_llm: bool = os.getenv("ENABLE_LLM", "true").lower() in {"1", "true", "yes"}
    fuzzy_threshold: int = int(os.getenv("FUZZY_THRESHOLD", "84"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
