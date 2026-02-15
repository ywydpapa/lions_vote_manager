"""
사용자 관련 Pydantic 스키마 (API 요청/응답)
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
from enum import Enum
import re


class UserRole(str, Enum):
    """사용자 역할"""
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserCreate(BaseModel):
    """사용자 생성 요청"""
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = Field(None, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v


class UserLogin(BaseModel):
    """사용자 로그인 요청"""
    username: str
    password: str


class UserUpdate(BaseModel):
    """사용자 정보 수정"""
    full_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = None
    role: Optional[UserRole] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v


class UserResponse(BaseModel):
    """사용자 응답"""
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """토큰 응답"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenPayload(BaseModel):
    """토큰 페이로드"""
    sub: int
    exp: int
    iat: int
    role: UserRole
