from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]  # AX-cap/


@dataclass(frozen=True)
class Settings:
    # 서버
    host: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    port: int = int(os.getenv("BACKEND_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    # 데이터 경로 
    project_root: Path = PROJECT_ROOT
    processed_data_dir: Path = PROJECT_ROOT / "data" / "processed"

    # 시뮬레이션 
    tick_interval_sec: float = float(os.getenv("SIM_TICK_SEC", "1.0"))
    default_target_current: float = 8000.0

    # DB 
    # 비워두면 NullRepository 로 fallback 
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/axcap",
    )
    database_enabled: bool = os.getenv("DATABASE_ENABLED", "true").lower() == "true"
    db_echo: bool = os.getenv("DB_ECHO", "false").lower() == "true"


settings = Settings()