"""
방문자 관련 Pydantic 스키마 (API 요청/응답)
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
import re


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class VisitorCreate(BaseModel):
    """방문자 생성 요청"""
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=7, max_length=20)
    email: Optional[str] = None
    company: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v


class VisitorUpdate(BaseModel):
    """방문자 정보 수정"""
    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = None
    company: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v


class VisitorResponse(BaseModel):
    """방문자 응답"""
    id: int
    name: str
    phone: str
    email: Optional[str]
    company: Optional[str]
    department: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VisitorListResponse(BaseModel):
    """방문자 목록 응답"""
    total: int
    items: list[VisitorResponse]
