"""
사용자 관리 및 인증 API 라우트
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse, UserUpdate
from app.services.user_service import UserService
from app.security.auth import create_access_token
from app.dependencies import get_current_user, get_current_admin_user
from app.models.user import User

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
        user_data: UserCreate,
        db: Session = Depends(get_db)
):
    """사용자 회원가입"""
    user = UserService.create_user(db, user_data)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
        user_login: UserLogin,
        db: Session = Depends(get_db)
):
    """사용자 로그인 및 토큰 발급"""
    user = UserService.authenticate_user(db, user_login)

    # JWT 액세스 토큰 생성
    access_token = create_access_token(user.id, user.role.value)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
        current_user: User = Depends(get_current_user)
):
    """현재 로그인한 사용자 정보 조회 (토큰 기반)"""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_current_user(
        user_data: UserUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """현재 사용자 정보 수정"""
    # 비즈니스 규칙: 관리자가 아닌 경우 역할(Role) 변경을 시도해도 무시함
    if user_data.role and user_data.role != current_user.role:
        if current_user.role.value != "admin":
            user_data.role = None

    updated_user = UserService.update_user(db, current_user.id, user_data)
    return updated_user