"""
방문 예약 관리 서비스
비즈니스 로직 계층
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from datetime import date
from app.models.reservation import Reservation, ReservationStatus
from app.schemas.reservation import ReservationCreate, ReservationUpdate
from app.utils.exceptions import NotFoundException, ValidationException


class ReservationService:
    """방문 예약 관리 서비스"""

    @staticmethod
    def create_reservation(db: Session, user_id: int, reservation_data: ReservationCreate) -> Reservation:
        """예약 생성"""
        reservation = Reservation(
            **reservation_data.model_dump(),
            created_by_user_id=user_id
        )
        db.add(reservation)
        db.commit()
        db.refresh(reservation)
        return reservation

    @staticmethod
    def get_reservation_by_id(db: Session, reservation_id: int) -> Reservation:
        """ID로 예약 조회"""
        reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
        if not reservation:
            raise NotFoundException(detail=f"Reservation with ID {reservation_id} not found")
        return reservation

    @staticmethod
    def get_all_reservations(db: Session, skip: int = 0, limit: int = 100) -> tuple[List[Reservation], int]:
        """전체 예약 조회"""
        total = db.query(Reservation).count()
        reservations = db.query(Reservation).offset(skip).limit(limit).all()
        return reservations, total

    @staticmethod
    def get_reservations_by_date(
            db: Session,
            start_date: date,
            end_date: Optional[date] = None,
            skip: int = 0,
            limit: int = 100
    ) -> tuple[List[Reservation], int]:
        """날짜 범위로 예약 조회"""
        if end_date is None:
            end_date = start_date

        query = db.query(Reservation).filter(
            and_(
                Reservation.visit_date >= start_date,
                Reservation.visit_date <= end_date
            )
        ).order_by(Reservation.visit_date, Reservation.visit_time)

        total = query.count()
        reservations = query.offset(skip).limit(limit).all()
        return reservations, total

    @staticmethod
    def get_reservations_by_visitor(
            db: Session,
            visitor_id: int,
            skip: int = 0,
            limit: int = 100
    ) -> tuple[List[Reservation], int]:
        """방문자별 예약 조회"""
        query = db.query(Reservation).filter(Reservation.visitor_id == visitor_id)
        total = query.count()
        reservations = query.offset(skip).limit(limit).all()
        return reservations, total

    @staticmethod
    def get_reservations_by_status(
            db: Session,
            status: ReservationStatus,
            skip: int = 0,
            limit: int = 100
    ) -> tuple[List[Reservation], int]:
        """상태별 예약 조회"""
        query = db.query(Reservation).filter(Reservation.status == status)
        total = query.count()
        reservations = query.offset(skip).limit(limit).all()
        return reservations, total

    @staticmethod
    def update_reservation(db: Session, reservation_id: int, reservation_data: ReservationUpdate) -> Reservation:
        """예약 정보 수정"""
        reservation = ReservationService.get_reservation_by_id(db, reservation_id)

        update_data = reservation_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(reservation, field, value)

        db.commit()
        db.refresh(reservation)
        return reservation

    @staticmethod
    def cancel_reservation(db: Session, reservation_id: int) -> Reservation:
        """예약 취소"""
        reservation = ReservationService.get_reservation_by_id(db, reservation_id)

        # 이미 완료된 예약은 취소 불가 처리 (비즈니스 규칙)
        if reservation.status == ReservationStatus.COMPLETED:
            raise ValidationException(detail="Cannot cancel a completed reservation")

        reservation.status = ReservationStatus.CANCELLED
        db.commit()
        db.refresh(reservation)
        return reservation

    @staticmethod
    def delete_reservation(db: Session, reservation_id: int) -> None:
        """예약 삭제"""
        reservation = ReservationService.get_reservation_by_id(db, reservation_id)
        db.delete(reservation)
        db.commit()