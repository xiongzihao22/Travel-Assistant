from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    app_mode: Literal["demo", "live"] = "demo"
    dashscope_api_key: SecretStr = SecretStr("")
    model: str = "qwen-plus"
    model_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    openweather_api_key: SecretStr = SecretStr("")
    amap_api_key: SecretStr = SecretStr("")
    amap_transport: Literal["streamable_http", "sse"] = "streamable_http"
    amap_mcp_url: str = "https://mcp.amap.com/mcp"
    output_dir: Path = Path("output")
    request_timeout: float = Field(90, ge=1, le=300)
    max_sessions: int = Field(100, ge=1, le=1000)
    max_turns: int = Field(30, ge=1, le=100)
    app_api_token: SecretStr = SecretStr("")

    @property
    def output_path(self) -> Path:
        return (ROOT / self.output_dir).resolve()
