"""
방문 예약 관련 Pydantic 스키마 (API 요청/응답)
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import date, time, datetime
from typing import Optional, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from app.schemas.visitor import VisitorResponse


class ReservationStatus(str, Enum):
    """예약 상태"""
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReservationCreate(BaseModel):
    """예약 생성 요청"""
    visitor_id: int
    visit_date: date = Field(..., description="방문 날짜")
    visit_time: Optional[time] = Field(None, description="방문 시간")
    purpose: str = Field(..., min_length=1, max_length=200)
    meeting_location: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)


class ReservationUpdate(BaseModel):
    """예약 정보 수정"""
    visit_date: Optional[date] = None
    visit_time: Optional[time] = None
    purpose: Optional[str] = Field(None, max_length=200)
    status: Optional[ReservationStatus] = None
    meeting_location: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)


class ReservationResponse(BaseModel):
    """예약 응답"""
    id: int
    visitor_id: int
    created_by_user_id: int
    visit_date: date
    visit_time: Optional[time]
    purpose: str
    status: ReservationStatus
    meeting_location: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReservationDetailResponse(ReservationResponse):
    """예약 상세 응답 (방문자 정보 포함)"""
    visitor: "VisitorResponse"


class ReservationListResponse(BaseModel):
    """예약 목록 응답"""
    total: int
    items: list[ReservationResponse]
