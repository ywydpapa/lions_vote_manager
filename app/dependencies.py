"""
인증 의존성 및 권한 검사
FastAPI 의존성 주입 패턴 사용
"""
from fastapi import Depends, Header
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.security.auth import verify_token
from app.services.user_service import UserService
from app.models.user import User, UserRole
from app.utils.exceptions import UnauthorizedException, ForbiddenException


async def get_current_user(
        db: Session = Depends(get_db),
        authorization: Optional[str] = Header(None)
) -> User:
    """
    현재 인증된 사용자 가져오기
    - Authorization 헤더에서 Bearer 토큰을 추출하고 검증합니다.
    """
    if not authorization:
        raise UnauthorizedException(detail="Missing authorization header")

    # Bearer 토큰 형식 추출 (Scheme과 Token 분리)
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise UnauthorizedException(detail="Invalid authentication scheme")
    except ValueError:
        raise UnauthorizedException(detail="Invalid authorization header format")

    # 토큰 검증 및 페이로드 추출
    token_payload = verify_token(token)
    if not token_payload:
        raise UnauthorizedException(detail="Invalid or expired token")

    # DB에서 사용자 정보 조회 및 활성화 상태 확인
    user = UserService.get_user_by_id(db, token_payload.sub)

    if not user.is_active:
        raise UnauthorizedException(detail="User account is inactive")

    return user


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    현재 사용자가 관리자(ADMIN)인지 확인
    """
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(detail="Admin access required")
    return current_user


def get_current_manager_user(current_user: User = Depends(get_current_user)) -> User:
    """
    현재 사용자가 관리자(ADMIN) 또는 매니저(MANAGER)인지 확인
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise ForbiddenException(detail="Manager or admin access required")
    return current_user