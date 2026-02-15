"""
방문자 관리 서비스
비즈니스 로직 계층
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.visitor import Visitor
from app.schemas.visitor import VisitorCreate, VisitorUpdate
from app.utils.exceptions import NotFoundException, ValidationException


class VisitorService:
    """방문자 관리 서비스"""

    @staticmethod
    def create_visitor(db: Session, visitor_data: VisitorCreate) -> Visitor:
        """방문자 생성"""
        visitor = Visitor(**visitor_data.model_dump())
        db.add(visitor)
        db.commit()
        db.refresh(visitor)
        return visitor

    @staticmethod
    def get_visitor_by_id(db: Session, visitor_id: int) -> Visitor:
        """ID로 방문자 조회"""
        visitor = db.query(Visitor).filter(Visitor.id == visitor_id).first()
        if not visitor:
            raise NotFoundException(detail=f"Visitor with ID {visitor_id} not found")
        return visitor

    @staticmethod
    def get_all_visitors(db: Session, skip: int = 0, limit: int = 100) -> tuple[List[Visitor], int]:
        """전체 방문자 조회 (페이징 지원)"""
        total = db.query(Visitor).count()
        visitors = db.query(Visitor).offset(skip).limit(limit).all()
        return visitors, total

    @staticmethod
    def search_visitors(db: Session, keyword: str, skip: int = 0, limit: int = 100) -> tuple[List[Visitor], int]:
        """방문자 검색 (이름, 연락처, 회사명, 이메일)"""
        query = db.query(Visitor).filter(
            (Visitor.name.ilike(f"%{keyword}%")) |
            (Visitor.phone.ilike(f"%{keyword}%")) |
            (Visitor.company.ilike(f"%{keyword}%")) |
            (Visitor.email.ilike(f"%{keyword}%"))
        )
        total = query.count()
        visitors = query.offset(skip).limit(limit).all()
        return visitors, total

    @staticmethod
    def update_visitor(db: Session, visitor_id: int, visitor_data: VisitorUpdate) -> Visitor:
        """방문자 정보 수정"""
        visitor = VisitorService.get_visitor_by_id(db, visitor_id)

        # 값이 명시적으로 들어온 필드만 업데이트
        update_data = visitor_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(visitor, field, value)

        db.commit()
        db.refresh(visitor)
        return visitor

    @staticmethod
    def delete_visitor(db: Session, visitor_id: int) -> None:
        """방문자 삭제"""
        visitor = VisitorService.get_visitor_by_id(db, visitor_id)
        db.delete(visitor)
        db.commit()