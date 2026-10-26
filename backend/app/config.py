import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    app_name: str = "Legal Snaps Infographic Generator"
    app_env: str = "development"
    debug: bool = True
    port: int = 8000
    host: str = "0.0.0.0"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Storage settings
    storage_dir: str = str(BASE_DIR / "storage" / "artifacts")
    sqlite_db_path: str = str(BASE_DIR / "storage" / "legal_snaps.db")

    # Hugging Face Inference Providers
    hf_token: str = Field(default="", validation_alias="HF_TOKEN")
    hf_router_base_url: str = "https://router.huggingface.co/v1"
    hf_provider_base_url: str = "https://router.huggingface.co"
    hf_text_model: str = "Qwen/Qwen2.5-72B-Instruct"
    # FLUX.1 (schnell for ultra-fast inference / dev for full detail) via fal-ai provider
    hf_image_model: str = "black-forest-labs/FLUX.1-schnell"
    hf_image_provider: str = "fal-ai"

    # Search & Discovery settings
    search_provider: str = "duckduckgo"
    search_api_key: str = ""

    # OCR settings
    ocr_provider: str = "disabled"
    tesseract_cmd: str = "/opt/homebrew/bin/tesseract"

    # Limits and timeouts
    api_timeout_seconds: int = 60
    max_source_size_bytes: int = 15_000_000
    analysis_max_chars: int = 60_000
    artwork_max_side: int = 1024

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def get_effective_hf_token(self) -> str:
        """Token from .env, the process environment, or a prior `hf auth login`."""
        for candidate in (
            self.hf_token,
            os.environ.get("HF_TOKEN"),
            os.environ.get("HUGGING_FACE_HUB_TOKEN"),
        ):
            if candidate and candidate.strip():
                return candidate.strip()

        token_file = Path.home() / ".cache" / "huggingface" / "token"
        try:
            if token_file.is_file():
                return token_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        return ""

settings = Settings()

# Ensure directories exist
os.makedirs(settings.storage_dir, exist_ok=True)
os.makedirs(Path(settings.sqlite_db_path).parent, exist_ok=True)
