"""
Application configuration using Pydantic Settings.
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="Audio Transcriber API")
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    environment: str = Field(default="development")

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # Whisper Model
    whisper_model_size: str = Field(default="base")  # Changed from medium to base for faster CPU processing
    whisper_device: str = Field(default="cpu")
    whisper_compute_type: str = Field(default="int8")

    # OpenAI (Optional)
    openai_api_key: Optional[str] = Field(default=None)
    openai_api_base: str = Field(default="https://api.openai.com/v1")

    # Hugging Face
    hf_endpoint: str = Field(default="https://hf-mirror.com")

    # Audio Processing
    max_audio_duration: int = Field(default=7200)  # 2 hours
    audio_sample_rate: int = Field(default=16000)
    temp_dir: str = Field(default="temp")

    # Logging
    log_level: str = Field(default="INFO")

    # Volcengine DeepSeek API (encrypted)
    volcengine_api_key_enc: Optional[str] = Field(default=None, alias="VOLCENGINE_API_KEY_ENC")
    volcengine_base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3")
    volcengine_model_name: str = Field(default="deepseek-v3")

    @computed_field
    @property
    def volcengine_api_key(self) -> Optional[str]:
        """解密并返回 API Key"""
        if not self.volcengine_api_key_enc:
            return None
        
        # 检查是否是明文（开发兼容）
        if not self.volcengine_api_key_enc.startswith("gAAAAAB"):
            return self.volcengine_api_key_enc
        
        # 解密
        try:
            from utils.encryption import decrypt_api_key
            return decrypt_api_key(self.volcengine_api_key_enc)
        except Exception as e:
            print(f"[WARNING] Failed to decrypt API key: {e}")
            return None


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
