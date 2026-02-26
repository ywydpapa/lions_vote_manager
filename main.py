from fastapi import UploadFile, File
from fastapi.responses import JSONResponse
from datetime import datetime
import shutil
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from pathlib import Path
import dotenv
import os
import uvicorn
from sqlalchemy import text
import re

dotenv.load_dotenv()
DATABASE_URL = os.getenv("dburl")
candiNo = int(os.getenv("candiNo"))
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_timeout=10,
    pool_recycle=1800)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/thumbnails", StaticFiles(directory="static/img/members/"), name="thumbnails")
THUMBNAIL_DIR = "./static/img/members"
BASE_DIR = Path(__file__).resolve().parent
# 업로드 저장 경로(원하는 위치로 변경 가능)
PHOTO_DIR = Path("./static/img/event_photos")
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def next_negative_index(event_no: int, directory: Path) -> int:
    pattern = re.compile(rf"^{re.escape(str(event_no))}-(\-?\d+)\..+$")
    indices = []
    for p in directory.iterdir():
        if not p.is_file():
            continue
        m = pattern.match(p.name)
        if m:
            try:
                indices.append(int(m.group(1)))
            except ValueError:
                pass
    if not indices:
        return -1
    return min(indices)


async def get_db():
    async with async_session() as session:
        yield session


async def get_reservations(candino:int,db: AsyncSession):
    try:
        query = text("SELECT * FROM voteReserv where attrib not like :attpatt and candiNo = :candino")
        result = await db.execute(query, {"attpatt": "%XXX%", "candino": candino})
        reserv_list = result.fetchall()  # 클럽 데이터를 모두 가져오기
        return reserv_list
    except:
        raise HTTPException(status_code=500, detail="Database query failed(RESERV_LIST)")

@app.get("/favicon.ico")
async def favicon():
    return {"detail": "Favicon is served at /static/favicon.ico"}


@app.get("/", response_class=HTMLResponse)
async def login_form(request: Request):
    if request.session.get("user_No"):
        return RedirectResponse(url="/success", status_code=303)
    return templates.TemplateResponse("login/login.html", {"request": request})


@app.get("/reservation", response_class=HTMLResponse)
async def reservations(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino,db)
    return templates.TemplateResponse("reserv/resume.html", {"request": request, "reservations": reservs})


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    return templates.TemplateResponse("history/projects.html", {"request": request})

@app.get("/success", response_class=HTMLResponse)
async def success(request: Request):
    return templates.TemplateResponse(
        "index/index.html", {"request": request, "user_No": request.session.get("user_No")}
    )


@app.get("/view_visitors", response_class=HTMLResponse)
async def view_visitors(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino,db)
    return templates.TemplateResponse("view/template_candi.html", {"request": request, "reservations": reservs})


@app.get("/viewer/candi_view", response_class=HTMLResponse)
async def view_candi(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino,db)
    return templates.TemplateResponse("templete/candi_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/aide_view", response_class=HTMLResponse)
async def view_aide(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino,db)
    return templates.TemplateResponse("templete/aide_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/history_view", response_class=HTMLResponse)
async def view_history(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino,db)
    return templates.TemplateResponse("templete/history_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/vision_view", response_class=HTMLResponse)
async def view_vision(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino,db)
    return templates.TemplateResponse("templete/vision_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/schedule_today", response_class=HTMLResponse)
async def view_today(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino,db)
    return templates.TemplateResponse("templete/sched_today.html", {"request": request, "reservations": reservs})


@app.get("/viewer/schedule_week", response_class=HTMLResponse)
async def view_week(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino,db)
    return templates.TemplateResponse("templete/sched_week.html", {"request": request, "reservations": reservs})


@app.post("/api/eventphotoupload/{eventNo}")
async def upload_event_photo(eventNo: int, photo: UploadFile = File(...)):
    # 1) 컨텐츠 타입 검증
    if photo.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type: {photo.content_type}",
        )
    # 2) 확장자 결정 (원본 파일명보다 content-type 우선)
    ext = EXT_BY_CONTENT_TYPE.get(photo.content_type, "")
    # 3) eventNo-1, eventNo-2 ... 형식으로 저장
    idx = next_negative_index(eventNo, PHOTO_DIR)
    filename = f"{eventNo}{idx}{ext}"  # 예: 123-1.jpg, 123-2.jpg ...
    save_path = PHOTO_DIR / filename
    # (안전장치) 혹시라도 같은 이름이 존재하면 더 내려가서 재시도
    while save_path.exists():
        idx -= 1
        filename = f"{eventNo}{idx}{ext}"
        save_path = PHOTO_DIR / filename
    # 4) 저장
    try:
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    # 5) 접근 가능한 URL 반환
    url_path = f"/static/img/event_photos/{filename}"
    return {
        "eventNo": eventNo,
        "filename": filename,
        "contentType": photo.content_type,
        "savedPath": str(save_path),
        "url": url_path,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
    )