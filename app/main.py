from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.database import Base, engine
from app.routes.users import router as users_router
from app.routes.visitors import router as visitors_router
from app.routes.reservations import router as reservations_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 라이프사이클 관리"""
    # 시작: 데이터베이스 테이블 생성
    Base.metadata.create_all(bind=engine)
    print("✓ Database initialized")
    yield
    # 종료: 필요한 정리 작업
    print("✓ Application shutdown")


app = FastAPI(
    title=settings.app_name,
    description="방문 예약 관리 시스템 API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 헬스체크 엔드포인트
@app.get("/api/health")
async def health_check():
    """애플리케이션 상태 확인"""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": "1.0.0"
    }


# 라우터 등록
app.include_router(users_router)
app.include_router(visitors_router)
app.include_router(reservations_router)


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Welcome to Reservation Management System API",
        "docs": "/api/docs",
        "openapi": "/api/openapi.json"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )