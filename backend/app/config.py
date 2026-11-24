import os
from typing import List, Tuple
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    llm_api_keys: str = "mock-key-1,mock-key-2"
    database_url: str = "sqlite:///./app.db"
    allowed_origins: str = "*"
    enable_failure_simulation: bool = True
    default_model: str = "gemini/gemini-2.0-flash"
    default_system_prompt: str = "You are a helpful and accurate AI assistant."

    @property
    def key_pool(self) -> List[Tuple[str, str]]:
        """
        Parses LLM_API_KEYS into key_id (key_1, key_2, ...) and raw API key.
        """
        keys = [k.strip() for k in self.llm_api_keys.split(",") if k.strip()]
        return [(f"key_{i+1}", key) for i, key in enumerate(keys)]

    @property
    def cors_origins(self) -> List[str]:
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def sqlite_db_path(self) -> str:
        url = self.database_url
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if url.startswith("sqlite:////"):
            path = "/" + url[11:]
            if path.startswith("/data") and not os.path.exists("/data"):
                try:
                    os.makedirs("/data", exist_ok=True)
                except Exception:
                    return os.path.join(backend_dir, "app.db")
            return path
        elif url.startswith("sqlite:///"):
            path = url[10:]
            if not os.path.isabs(path):
                clean_rel = path.lstrip("./") if path.startswith("./") else path
                return os.path.join(backend_dir, clean_rel)
            return path
        return url

settings = Settings()
