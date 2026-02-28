from fastapi import UploadFile, File, Body
from fastapi.responses import JSONResponse
from datetime import datetime
import shutil
from fastapi import FastAPI, Request, Depends, HTTPException, Form, Response
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
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, DateTime, ForeignKey,CheckConstraint, String
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm import DeclarativeBase

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

class Base(DeclarativeBase):
    pass

class RegReservIn(BaseModel):
    dateno: str        # 예: "02271" (MMDD + 오전/오후코드)
    visitTime: str     # 예: "09:00"
    visitorCount: int
    memberNos: List[int]
    reservMemo: str | None = None

class RegReservOut(BaseModel):
    reservNo: int

class VoteReserv(Base):
    __tablename__ = "voteReserv"
    reservNo: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clubNo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    circleNo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reservFrom: Mapped["datetime"] = mapped_column(DateTime, nullable=False)  # DateTime
    visitorCount: Mapped[int] = mapped_column(Integer, nullable=False)
    reservMemo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "(clubNo IS NULL) <> (circleNo IS NULL)",
            name="ck_voteReserv_exactly_one_of_clubNo_circleNo",
        ),
    )


class VisitMembers(Base):
    __tablename__ = "visitMembers"
    visitNo: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reservNo: Mapped[int] = mapped_column(ForeignKey("voteReserv.reservNo"), nullable=False)
    memberNo: Mapped[int] = mapped_column(Integer, nullable=False)


def dateno_time_to_datetime(dateno: str, visit_time: str) -> datetime:
    # dateno: "MMDDX" (X=오전/오후코드), visit_time: "HH:MM"
    if not dateno or len(dateno) < 4:
        raise ValueError("invalid dateno")
    mm = int(dateno[0:2])
    dd = int(dateno[2:4])

    hh, mi = visit_time.split(":")
    hh = int(hh); mi = int(mi)

    y = date.today().year
    return datetime(y, mm, dd, hh, mi, 0)


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


async def get_reservations(db: AsyncSession):
    try:
        query = text("select a.*, b.circleName, c.clubName from voteReserv a left join lionsCircle b on a.circleNo = b.circleNo left join lionsaddr.lionsClub c on a.clubNo = c.clubNo where a.attrib not like :attpatt")
        result = await db.execute(query, {"attpatt": "%XXX%"})
        reserv_list = result.fetchall()  # 클럽 데이터를 모두 가져오기
        return reserv_list
    except:
        raise HTTPException(status_code=500, detail="Database query failed(RESERV_LIST)")


async def get_club_reserv(clubno:int,db: AsyncSession):
    try:
        query = text("SELECT * FROM voteReserv where attrib not like :attpatt and clubNo = :clubno")
        result = await db.execute(query, {"attpatt": "%XXX%", "clubno": clubno})
        reserv_list = result.fetchall()  # 클럽 데이터를 모두 가져오기
        return reserv_list
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database query failed(RESERV_LIST)")


async def get_circle_reserv(circleno: int, db: AsyncSession):
    try:
        query = text("""
            SELECT reservNo, reservFrom, visitorCount
            FROM voteReserv
            WHERE attrib NOT LIKE :attpatt
              AND circleNo = :circleno
            ORDER BY reservFrom DESC
        """)
        result = await db.execute(query, {"attpatt": "%XXX%", "circleno": circleno})
        return result.mappings().all()  # <-- list[dict]
    except Exception:
        raise HTTPException(status_code=500, detail="Database query failed(RESERV_LIST)")


async def get_clubmembers(clubno:int,db: AsyncSession):
    try:
        query = text("SELECT a.memberNo, a.memberName, a.rankNo, b.rankTitlekor FROM lionsMember a left join lionsRank b on a.rankNo = b.rankNo where a.clubNo = :clubno")
        result = await db.execute(query, {"clubno": clubno})
        member_list = result.fetchall()  # 클럽 데이터를 모두 가져오기
        return member_list
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(CLUBMEMBER_LIST)")


async def get_allmembers(db: AsyncSession):
    try:
        query = text("SELECT a.memberNo, a.memberName, a.rankNo, a.clubNo, b.rankTitlekor, c.clubName FROM lionsMember a left join lionsRank b on a.rankNo = b.rankNo  left join lionsClub c on a.clubNo = c.clubNo where a.clubNo != :cno order by c.clubNo")
        result = await db.execute(query,{"cno": 0})
        member_list = result.fetchall()  # 회원 데이터를 모두 가져오기
        return member_list
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(ALLMEMBER_LIST)")


async def get_distmembers(db: AsyncSession):
    try:
        query = text("SELECT a.memberNo, a.memberName, a.rankNo, a.clubNo, b.rankTitlekor, c.clubName FROM lionsMember a "
                     "left join lionsRank b on a.rankNo = b.rankNo  left join lionsClub c on a.clubNo = c.clubNo "
                     "where a.clubNo != :cno and a.rankNo not in (19,29,48)order by c.clubNo")
        result = await db.execute(query,{"cno": 0})
        member_list = result.fetchall()  # 회원 데이터를 모두 가져오기
        return member_list
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(ALLMEMBER_LIST)")


async def get_clublist(db: AsyncSession):
    try:
        query = text("select * from lionsClub where attrib not like :attpatt")
        result = await db.execute(query, {"attpatt": "%XXX%"})
        club_list = result.fetchall()
        return club_list
    except:
        raise HTTPException(status_code=500, detail="Database query failed(CLUBLIST)")


async def get_circlelist(db: AsyncSession):
    try:
        query = text("select * from lionsCircle where attrib = :attpatt and circleType=:ctype")
        result = await db.execute(query, {"attpatt": "1000010000", "ctype": "VOTEC"})
        circle_list = result.fetchall()
        return circle_list
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(CIRCLELIST)")


@app.get("/favicon.ico")
async def favicon():
    return {"detail": "Favicon is served at /static/favicon.ico"}


@app.get("/", response_class=HTMLResponse)
async def login_form(request: Request):
    if request.session.get("vote_user_No"):
        return RedirectResponse(url="/success", status_code=303)
    return templates.TemplateResponse("login/login.html", {"request": request})


@app.post("/login")
async def login_post(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        db: AsyncSession = Depends(get_db)
):
    query = text(
        "SELECT userNo, userName, userRole FROM voteUser WHERE userId = :username AND userPasswd = password(:password)")
    result = await db.execute(query, {"username": username, "password": password})
    user = result.fetchone()
    query2 = text("UPDATE voteUser SET loginStamp = :now , logoutStamp = NULL WHERE userNo = :userNo")
    await db.execute(query2, {"now": datetime.now(), "userNo": user[0]})
    await db.commit()
    if user is None:
        return templates.TemplateResponse("login/login.html", {"request": request, "error": "Invalid credentials"})
    request.session["vote_user_No"] = user[0]
    request.session["vote_user_Name"] = user[1]
    request.session["vote_user_Role"] = user[2]
    return RedirectResponse(url="/success", status_code=303)


@app.get("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        user_No = request.session.get("vote_user_No")
        query2 = text("UPDATE voteUser SET logoutStamp = :now WHERE userNo = :userNo")
        await db.execute(query2, {"now": datetime.now(), "userNo": user_No})
        await db.commit()
        request.session.clear()  # 세션 삭제
        return RedirectResponse(url="/")
    except Exception as e:
        return RedirectResponse(url="/", status_code=303)


@app.get("/reservation", response_class=HTMLResponse)
async def reservations(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino,db)
    return templates.TemplateResponse("reserv/resume.html", {"request": request, "reservations": reservs})


@app.get("/circle_reservs/{circleno}")
async def circle_reservs(circleno: int, db: AsyncSession = Depends(get_db)):
    rows = await get_circle_reserv(circleno, db)
    return rows


@app.get("/reserv_new/{dateno}", response_class=HTMLResponse)
async def new_reservations(request: Request, dateno: str, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    clubs = await get_clublist(db)
    return templates.TemplateResponse("reserv/new_reserv.html", {"request": request, "candino": candino, "dateno": dateno, "clubs": clubs})


@app.post("/reserv_canc/{reservno}")
async def cancel_reservations(reservno: int, db: AsyncSession = Depends(get_db)):
    try:
        query = text("""
            update voteReserv
            set modDate = :now, attrib = :attr
            where reservNo = :reservno
        """)
        await db.execute(query, {
            "now": datetime.now(),
            "attr": "XXXCAXXXNC",
            "reservno": reservno,
        })
        await db.commit()
        return JSONResponse({"canceled": True})
    except Exception as e:
        return JSONResponse({"canceled": False, "error": str(e)}, status_code=500)


@app.get("/reserv_newclub/{clubno}/{dateno}", response_class=HTMLResponse)
async def new_reservations(request: Request,clubno:int ,dateno: str, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    cmembers = await get_clubmembers(clubno,db)
    reservs = await get_club_reserv(clubno,db)
    return templates.TemplateResponse("reserv/new_reserv_club.html", {"request": request, "candino": candino, "dateno": dateno, "clubno": clubno, "cmembers": cmembers, "reservs": reservs})


@app.get("/reserv_newcircle/{dateno}", response_class=HTMLResponse)
async def new_reservations(request: Request,dateno: str, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    members = await get_distmembers(db)
    circlelist = await get_circlelist(db)
    return templates.TemplateResponse("reserv/new_reserv_cirl.html", {"request": request, "candino": candino, "dateno": dateno, "members": members, "circles": circlelist})


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
    reservs = await get_reservations(db)
    return templates.TemplateResponse("view/template_candi.html", {"request": request, "reservations": reservs})


@app.get("/viewer/candi_view", response_class=HTMLResponse)
async def view_candi(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(db)
    return templates.TemplateResponse("templete/candi_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/aide_view", response_class=HTMLResponse)
async def view_aide(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(db)
    return templates.TemplateResponse("templete/aide_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/history_view", response_class=HTMLResponse)
async def view_history(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(db)
    return templates.TemplateResponse("templete/history_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/vision_view", response_class=HTMLResponse)
async def view_vision(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(db)
    return templates.TemplateResponse("templete/vision_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/schedule_today", response_class=HTMLResponse)
async def view_today(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(db)
    return templates.TemplateResponse("templete/sched_today.html", {"request": request, "reservations": reservs})


@app.get("/viewer/schedule_week", response_class=HTMLResponse)
async def view_week(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(db)
    return templates.TemplateResponse("templete/sched_week.html", {"request": request, "reservations": reservs})





@app.post("/api/eventphotoupload/{eventNo}")
async def upload_event_photo(eventNo: int, photo: UploadFile = File(...)):
    if photo.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type: {photo.content_type}",
        )
    ext = EXT_BY_CONTENT_TYPE.get(photo.content_type, "")
    idx = next_negative_index(eventNo, PHOTO_DIR)
    filename = f"{eventNo}{idx}{ext}"  # 예: 123-1.jpg, 123-2.jpg ...
    save_path = PHOTO_DIR / filename
    while save_path.exists():
        idx -= 1
        filename = f"{eventNo}{idx}{ext}"
        save_path = PHOTO_DIR / filename
    try:
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    url_path = f"/static/img/event_photos/{filename}"
    return {
        "eventNo": eventNo,
        "filename": filename,
        "contentType": photo.content_type,
        "savedPath": str(save_path),
        "url": url_path,
    }


@app.post("/insert_newcircle")
async def insert_circ(
    request: Request,
    circlename: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    try:
        name = circlename.strip()
        if not name:
            raise HTTPException(status_code=400, detail="circlename is empty")

        query = text("""
            INSERT INTO lionsCircle (circleName, circleType)
            VALUES (:circlename, 'VOTEC')
        """)
        await db.execute(query, {"circlename": name})
        await db.commit()
        return {"inserted": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert new circle: {e}")


@app.post("/reg_reserv/{clubNo}", response_model=RegReservOut)
async def reg_reserv(clubNo: int, payload: RegReservIn, db: AsyncSession = Depends(get_db)):
    if payload.visitorCount != len(payload.memberNos):
        raise HTTPException(status_code=400, detail="visitorCount와 선택 인원 수가 다릅니다.")
    if payload.visitorCount <= 0:
        raise HTTPException(status_code=400, detail="방문 회원을 1명 이상 선택하세요.")

    try:
        reserv_from_dt = dateno_time_to_datetime(payload.dateno, payload.visitTime)

        vr = VoteReserv(
            clubNo=clubNo,
            circleNo=None,
            reservFrom=reserv_from_dt,
            visitorCount=payload.visitorCount,
            reservMemo=payload.reservMemo,
        )
        db.add(vr)
        await db.flush()  # reservNo 생성

        db.add_all([VisitMembers(reservNo=vr.reservNo, memberNo=mn) for mn in payload.memberNos])

        await db.commit()
        return RegReservOut(reservNo=vr.reservNo)

    except ValueError as ve:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(e)
        await db.rollback()
        raise HTTPException(status_code=500, detail="DB 저장 중 오류가 발생했습니다.")


@app.post("/reg_reservc/{circleNo}", response_model=RegReservOut)
async def reg_reserv(circleNo: int, payload: RegReservIn, db: AsyncSession = Depends(get_db)):
    if payload.visitorCount != len(payload.memberNos):
        raise HTTPException(status_code=400, detail="visitorCount와 선택 인원 수가 다릅니다.")
    if payload.visitorCount <= 0:
        raise HTTPException(status_code=400, detail="방문 회원을 1명 이상 선택하세요.")

    try:
        reserv_from_dt = dateno_time_to_datetime(payload.dateno, payload.visitTime)

        vr = VoteReserv(
            circleNo=circleNo,
            clubNo=None,
            reservFrom=reserv_from_dt,
            visitorCount=payload.visitorCount,
            reservMemo=payload.reservMemo,
        )
        db.add(vr)
        await db.flush()  # reservNo 생성

        db.add_all([VisitMembers(reservNo=vr.reservNo, memberNo=mn) for mn in payload.memberNos])

        await db.commit()
        return RegReservOut(reservNo=vr.reservNo)

    except ValueError as ve:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(e)
        await db.rollback()
        raise HTTPException(status_code=500, detail="DB 저장 중 오류가 발생했습니다.")


@app.get("/circles")
async def get_circles(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text("""
        SELECT circleNo, circleName
        FROM lionsCircle
        WHERE circleType = 'VOTEC'
        ORDER BY circleName
    """))).all()
    return [{"id": r[0], "name": r[1]} for r in rows]


@app.get("/api/get_reserv")
async def get_reserv(db: AsyncSession = Depends(get_db)):
    try:
        rows = await get_reservations(db)
        result = [{"reservNo": row[0], "reservFrom": row[4], "visitCnt": row[7], "reservMemo": row[8], "visitorName": (row[12] or row[13])} for row in rows]
    except Exception as e:
        print(e)
        result = []
    finally:
        return {"reservs": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
    )