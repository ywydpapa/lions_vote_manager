"""
방문 예약 모델 (데이터베이스 테이블)
"""
from sqlalchemy import Column, Integer, String, DateTime, Date, Time, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base


class ReservationStatus(str, enum.Enum):
    """예약 상태"""
    SCHEDULED = "scheduled"  # 예약됨
    CONFIRMED = "confirmed"  # 확인됨
    COMPLETED = "completed"  # 완료
    CANCELLED = "cancelled"  # 취소됨


class Reservation(Base):
    """방문 예약 테이블"""
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    visitor_id = Column(Integer, ForeignKey("visitors.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    visit_date = Column(Date, nullable=False, index=True)
    visit_time = Column(Time, nullable=True)
    purpose = Column(String(200), nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.SCHEDULED, nullable=False, index=True)
    meeting_location = Column(String(100), nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 관계
    visitor = relationship("Visitor", back_populates="reservations")
    created_by = relationship("User", back_populates="reservations")

    def __repr__(self):
        return f"<Reservation(id={self.id}, visitor_id={self.visitor_id}, status={self.status})>"