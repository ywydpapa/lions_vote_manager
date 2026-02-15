"""
사용자 모델 (데이터베이스 테이블)
"""
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base


class UserRole(str, enum.Enum):
    """사용자 역할"""
    ADMIN = "admin"  # 관리자
    MANAGER = "manager"  # 담당자
    VIEWER = "viewer"  # 조회자


class User(Base):
    """사용자 테이블"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(SQLEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Integer, default=1, nullable=False)  # SQLite 호환성
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 관계
    reservations = relationship("Reservation", back_populates="created_by")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"