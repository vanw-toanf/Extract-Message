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
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "256"))
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    enable_llm: bool = os.getenv("ENABLE_LLM", "true").lower() in {"1", "true", "yes"}
    cpu_fast_mode: bool = os.getenv("CPU_FAST_MODE", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    fuzzy_threshold: int = int(os.getenv("FUZZY_THRESHOLD", "84"))
    llm_max_concurrent: int = int(os.getenv("LLM_MAX_CONCURRENT", "20"))
    llm_queue_timeout: float = float(os.getenv("LLM_QUEUE_TIMEOUT_SECONDS", "30"))
    goong_api: str = os.getenv("GOONG_API", "")
    goong_timeout_seconds: float = float(os.getenv("GOONG_TIMEOUT_SECONDS", "5"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
