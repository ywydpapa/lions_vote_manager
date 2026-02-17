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

dotenv.load_dotenv()
DATABASE_URL = os.getenv("dburl")
candiNo = int(os.getenv("candino"))
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



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
    )