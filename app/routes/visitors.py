"""
방문자 관리 API 라우트
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.schemas.visitor import VisitorCreate, VisitorUpdate, VisitorResponse, VisitorListResponse
from app.services.visitor_service import VisitorService
from app.utils.exceptions import NotFoundException

router = APIRouter(
    prefix="/api/visitors",
    tags=["Visitors"]
)


@router.post("", response_model=VisitorResponse, status_code=status.HTTP_201_CREATED)
async def create_visitor(
        visitor_data: VisitorCreate,
        db: Session = Depends(get_db)
):
    """새로운 방문자 등록"""
    visitor = VisitorService.create_visitor(db, visitor_data)
    return visitor


@router.get("", response_model=VisitorListResponse)
async def list_visitors(
        db: Session = Depends(get_db),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        search: Optional[str] = Query(None)
):
    """
    방문자 목록 조회
    - search 파라미터가 있으면 검색 로직을, 없으면 전체 목록 조회를 수행합니다.
    """
    if search:
        visitors, total = VisitorService.search_visitors(db, search, skip, limit)
    else:
        visitors, total = VisitorService.get_all_visitors(db, skip, limit)

    return {
        "total": total,
        "items": visitors
    }


@router.get("/{visitor_id}", response_model=VisitorResponse)
async def get_visitor(
        visitor_id: int,
        db: Session = Depends(get_db)
):
    """방문자 상세 조회"""
    visitor = VisitorService.get_visitor_by_id(db, visitor_id)
    return visitor


@router.put("/{visitor_id}", response_model=VisitorResponse)
async def update_visitor(
        visitor_id: int,
        visitor_data: VisitorUpdate,
        db: Session = Depends(get_db)
):
    """방문자 정보 수정"""
    visitor = VisitorService.update_visitor(db, visitor_id, visitor_data)
    return visitor


@router.delete("/{visitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visitor(
        visitor_id: int,
        db: Session = Depends(get_db)
):
    """방문자 삭제"""
    VisitorService.delete_visitor(db, visitor_id)
    return None