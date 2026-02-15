"""
애플리케이션 설정 파일
환경 변수를 통해 설정 관리
"""
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # 데이터베이스 설정
    database_url: str = "sqlite:///./reservation.db"

    # JWT 설정
    secret_key: str = "your-secret-key-here-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # 애플리케이션 설정
    app_name: str = "Reservation Management System"
    debug: bool = False

    # CORS 설정
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    class Config:
        # ✅ 실행 위치와 무관하게 "프로젝트 루트의 .env"를 찾도록 고정
        env_file = str(Path(__file__).resolve().parents[1] / ".env")
        case_sensitive = False


settings = Settings()
