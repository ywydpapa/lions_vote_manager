"""
방문자 모델 (데이터베이스 테이블)
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Visitor(Base):
    """방문자 테이블"""
    __tablename__ = "visitors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), nullable=True, index=True)
    company = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 관계
    reservations = relationship("Reservation", back_populates="visitor", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Visitor(id={self.id}, name={self.name}, company={self.company})>"