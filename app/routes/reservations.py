"""
방문 예약 관리 API 라우트
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from app.database import get_db
from app.schemas.reservation import (
    ReservationCreate,
    ReservationUpdate,
    ReservationResponse,
    ReservationListResponse,
    ReservationStatus
)
from app.services.reservation_service import ReservationService
from app.utils.exceptions import NotFoundException

router = APIRouter(
    prefix="/api/reservations",
    tags=["Reservations"]
)


@router.post("", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
        reservation_data: ReservationCreate,
        db: Session = Depends(get_db)
):
    """새로운 방문 예약 생성"""
    # TODO: 인증 로직 추가 후 현재 로그인한 user_id로 변경 필요
    reservation = ReservationService.create_reservation(db, 1, reservation_data)
    return reservation


@router.get("", response_model=ReservationListResponse)
async def list_reservations(
        db: Session = Depends(get_db),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        start_date: Optional[date] = Query(None),
        end_date: Optional[date] = Query(None),
        visitor_id: Optional[int] = Query(None),
        status: Optional[ReservationStatus] = Query(None)
):
    """
    방문 예약 목록 조회 (필터링 지원)
    - 날짜 범위, 방문자 ID, 예약 상태별로 필터링이 가능합니다.
    """
    if start_date:
        reservations, total = ReservationService.get_reservations_by_date(
            db, start_date, end_date, skip, limit
        )
    elif visitor_id:
        reservations, total = ReservationService.get_reservations_by_visitor(
            db, visitor_id, skip, limit
        )
    elif status:
        reservations, total = ReservationService.get_reservations_by_status(
            db, status, skip, limit
        )
    else:
        reservations, total = ReservationService.get_all_reservations(db, skip, limit)

    return {
        "total": total,
        "items": reservations
    }


@router.get("/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(
        reservation_id: int,
        db: Session = Depends(get_db)
):
    """방문 예약 상세 조회"""
    reservation = ReservationService.get_reservation_by_id(db, reservation_id)
    return reservation


@router.put("/{reservation_id}", response_model=ReservationResponse)
async def update_reservation(
        reservation_id: int,
        reservation_data: ReservationUpdate,
        db: Session = Depends(get_db)
):
    """방문 예약 정보 수정"""
    reservation = ReservationService.update_reservation(db, reservation_id, reservation_data)
    return reservation


@router.post("/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
        reservation_id: int,
        db: Session = Depends(get_db)
):
    """방문 예약 취소 (상태 변경)"""
    reservation = ReservationService.cancel_reservation(db, reservation_id)
    return reservation


@router.delete("/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reservation(
        reservation_id: int,
        db: Session = Depends(get_db)
):
    """방문 예약 데이터 삭제"""
    ReservationService.delete_reservation(db, reservation_id)
    return None