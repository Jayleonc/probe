import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class LimitsConfig(BaseModel):
    max_lines: int = 50
    max_bytes: int = 65536
    max_time_range_hours: int = 24
    command_timeout_seconds: int = 10


class SecurityConfig(BaseModel):
    redact_enabled: bool = True


class PathsConfig(BaseModel):
    hourly_log_dir: str = "/data/brick/log"
    supervisor_log_dir: str = "/var/log/supervisor"
    glog_path: str = "/data/pinfire/tools/glog.sh"


class ServerConfig(BaseModel):
    name: str = "probe"
    environment: str = "dev"
    host: str = "0.0.0.0"
    port: int = 3000
    audit_log_path: str = "./audit.log"


class Settings(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)


def load_settings(config_path: str | Path | None = None) -> Settings:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "settings" / "config.yaml"

    config_path = Path(config_path)
    if not config_path.exists():
        print(f"Warning: config not found at {config_path}, using defaults", file=sys.stderr)
        return Settings()

    with open(config_path) as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    return Settings(**data)


settings = load_settings()
