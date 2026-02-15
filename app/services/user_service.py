"""
사용자 관리 서비스
비즈니스 로직 계층
"""
from sqlalchemy.orm import Session
from typing import Optional
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate, UserLogin
from app.security.auth import hash_password, verify_password, create_access_token
from app.utils.exceptions import NotFoundException, DuplicateException, UnauthorizedException


class UserService:
    """사용자 관리 서비스"""

    @staticmethod
    def create_user(db: Session, user_data: UserCreate) -> User:
        """사용자 생성 (회원가입)"""
        # 중복 확인 (Username 또는 Email)
        existing_user = db.query(User).filter(
            (User.username == user_data.username) | (User.email == user_data.email)
        ).first()

        if existing_user:
            if existing_user.username == user_data.username:
                raise DuplicateException(detail="Username already exists")
            else:
                raise DuplicateException(detail="Email already exists")

        # 비밀번호 해싱
        hashed_password = hash_password(user_data.password)

        user = User(
            username=user_data.username,
            email=user_data.email,
            password_hash=hashed_password,
            full_name=user_data.full_name,
            role=UserRole.VIEWER  # 기본 권한 설정
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate_user(db: Session, user_login: UserLogin) -> Optional[User]:
        """사용자 인증 (로그인 로직)"""
        user = db.query(User).filter(User.username == user_login.username).first()

        # 유저 미존재 또는 비밀번호 불일치
        if not user or not verify_password(user_login.password, user.password_hash):
            raise UnauthorizedException(detail="Invalid username or password")

        # 계정 활성화 여부 확인
        if not user.is_active:
            raise UnauthorizedException(detail="User account is inactive")

        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """ID로 사용자 조회"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise NotFoundException(detail=f"User with ID {user_id} not found")
        return user

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> User:
        """사용자명으로 사용자 조회"""
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise NotFoundException(detail=f"User with username {username} not found")
        return user

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> User:
        """이메일로 사용자 조회"""
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise NotFoundException(detail=f"User with email {email} not found")
        return user

    @staticmethod
    def update_user(db: Session, user_id: int, user_data: UserUpdate) -> User:
        """사용자 정보 수정"""
        user = UserService.get_user_by_id(db, user_id)

        # 전달된 필드만 업데이트 (Partial Update)
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def deactivate_user(db: Session, user_id: int) -> User:
        """사용자 비활성화 (Soft Delete 대용)"""
        user = UserService.get_user_by_id(db, user_id)
        user.is_active = False
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def activate_user(db: Session, user_id: int) -> User:
        """사용자 활성화"""
        user = UserService.get_user_by_id(db, user_id)
        user.is_active = True
        db.commit()
        db.refresh(user)
        return user