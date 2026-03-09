from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi import UploadFile, File, Body, Query
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
from fastapi.responses import StreamingResponse
import asyncio
import json
from fastapi.encoders import jsonable_encoder
from PIL import Image, ImageFont, ImageDraw
import io


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
templates = Jinja2Templates(directory="templates", context_processors=[lambda request: {"session": request.session},],)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/thumbnails", StaticFiles(directory="static/img/members/"), name="thumbnails")
MEMBERPHOTO_DIR = "./static/img/members"
BASE_DIR = Path(__file__).resolve().parent
# 업로드 저장 경로(원하는 위치로 변경 가능)
PHOTO_DIR = Path("./static/img/event_photos")
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class SseHub:
    def __init__(self):
        self.queues: set[asyncio.Queue] = set()
    def connect(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.queues.add(q)
        return q
    def disconnect(self, q: asyncio.Queue):
        self.queues.discard(q)
    async def broadcast(self, event: str, data: dict):
        msg = {"event": event, "data": data}
        for q in list(self.queues):
            await q.put(msg)
hub = SseHub()


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


async def resize_image_if_needed(contents: bytes, max_bytes: int = 314572) -> bytes:
    if len(contents) <= max_bytes:
        return contents
    image = Image.open(io.BytesIO(contents))
    format = image.format if image.format else 'JPEG'
    quality = 85  # JPEG의 경우
    for trial in range(10):
        buffer = io.BytesIO()
        save_kwargs = {'format': format}
        if format.upper() in ['JPEG', 'JPG']:
            save_kwargs['quality'] = quality
            save_kwargs['optimize'] = True
        image.save(buffer, **save_kwargs)
        data = buffer.getvalue()
        if len(data) <= max_bytes:
            return data
        if format.upper() in ['JPEG', 'JPG'] and quality > 30:
            quality -= 10
        else:
            w, h = image.size
            image = image.resize((int(w * 0.9), int(h * 0.9)), Image.LANCZOS)
    return data


async def save_memberPhoto(image_data: bytes, memberno: int, size=(200, 300)):
    # 디렉토리가 없으면 생성
    os.makedirs(MEMBERPHOTO_DIR, exist_ok=True)
    # 원본 이미지를 Pillow로 열기
    image = Image.open(io.BytesIO(image_data))
    # 썸네일 생성
    image.thumbnail(size)
    # 저장 경로
    thumbnail_path = os.path.join(MEMBERPHOTO_DIR, f"mphoto_{memberno}.png")
    # 썸네일 저장
    image.save(thumbnail_path, format="PNG")
    return thumbnail_path


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


async def get_reservations(candino: int,db: AsyncSession):
    try:
        query = text("select * from voteReserv where attrib not like :attpatt and candino = :candino order by reservFrom")
        result = await db.execute(query, {"attpatt": "%XXX%", "candino": candino})
        reserv_list = result.fetchall()  # 클럽 데이터를 모두 가져오기
        return reserv_list
    except:
        raise HTTPException(status_code=500, detail="Database query failed(RESERV_LIST)")


async def get_apireserv(db: AsyncSession):
    try:
        query = text("select a.*, b.circleName, c.clubName from voteReserv a left join lionsCircle b on a.circleNo = b.circleNo left join lionsaddr.lionsClub c on a.clubNo = c.clubNo where a.attrib not like :attpatt order by a.reservFrom")
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


async def get_reserv_dtl(reservno: int, db: AsyncSession):
    query = text("""select a.reservNo, a.reservFrom, a.visitorCount, b.circleName, c.clubName, a.reservMemo, a.clubNo, a.circleNo, a.attrib from voteReserv a left join lionsCircle b on a.circleNo = b.circleNo left join lionsClub c on a.clubNo = c.clubNo where reservNo = :reservno""")
    result = await db.execute(query, {"reservno": reservno})
    row = result.fetchone()
    result = {"reservNo": row[0], "reservFrom": row[1], "visitCnt": row[2], "reservMemo": row[5], "visitorName": (row[3] or row[4]), "clubNo": row[6], "circleNo": row[7], "attrib": row[8]}
    return result


async def get_club_dtl(clubno: int, db: AsyncSession):
    query = text("""select 
    a.*,
    x.infoContent
from lionsClub a
left join (
    select 
        clubNo,
        group_concat(
            concat(
                case infoType
                    when 'SLGAN' then '슬로건: '
                    when 'STF01' then '회장: '
                    when 'STF02' then '총무: '
                    when 'STF03' then '재무: '
                    when 'ESTMB' then '창립회장: '
                    when 'ESTMC' then '창립회원수: '
                    when 'MBCNT' then '현재 회원수: '
                    when 'AINFO' then '봉사실적: '
                    else concat(infoType, ': ')
                end,
                infoContent
            )
            order by field(infoType, 'SLGAN', 'STF01', 'STF02', 'STF03', 'ESTMB', 'ESTMC', 'MBCNT', 'AINFO')
            separator '\n'
        ) as infoContent
    from voteClubaddinfo
    where attrib = :attr
      and infoContent is not null
      and trim(infoContent) <> ''
    group by clubNo
) x
    on a.clubNo = x.clubNo
where a.clubNo = :clubno""")
    result = await db.execute(query, {"clubno": clubno, "attr": "1000010000"})
    row = result.fetchone()
    query2 = text("""select count(*) from lionsMember where clubNo = :clubno""")
    result2 = await db.execute(query2, {"clubno": clubno})
    row2 = result2.fetchone()
    result = {"clubNo": row[0], "clubName": row[1], "estDate": row[2], "regionNo": row[3], "memberCount": row2[0], "infoContent": row[11]}
    return result


async def get_visitors(reservno: int, db: AsyncSession):
    query = text("""select a.memberNo,b.memberName,d.clubName, c.rankTitlekor, a.rightYN, a.visitMemo from visitMembers a left join lionsMember b on a.memberNo = b.memberNo left join lionsRank c on c.rankNo = b.rankNo left join lionsClub d on d.clubNo = b.clubNo where reservNo = :reservno""")
    result = await db.execute(query, {"reservno": reservno})
    visitors = result.fetchall()
    return visitors


async def get_clubmembers(clubno:int,db: AsyncSession):
    try:
        query = text("SELECT a.memberNo, a.memberName, a.rankNo, b.rankTitlekor, a.clubNo FROM lionsMember a left join lionsRank b on a.rankNo = b.rankNo where a.clubNo = :clubno")
        result = await db.execute(query, {"clubno": clubno})
        member_list = result.fetchall()  # 클럽 데이터를 모두 가져오기
        return member_list
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(CLUBMEMBER_LIST)")


async def get_memberdtl(memberno:int,db: AsyncSession):
    try:
        query = text("SELECT a.memberNo, a.memberName, a.rankNo, a.clubNo FROM lionsMember a where a.memberNo = :memberno")
        result = await db.execute(query, {"memberno": memberno})
        member_dtl = result.fetchone()  # 클럽 데이터를 모두 가져오기
        print(member_dtl)
        return member_dtl
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(MEMBER_DETAIL)")


async def get_clubdtl(clubno:int,db: AsyncSession):
    try:
        query = text("SELECT * FROM lionsClub where clubNo = :clubno")
        result = await db.execute(query, {"clubno": clubno})
        clubdtl = result.fetchone()  # 클럽 데이터를 모두 가져오기
        return clubdtl
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(CLUB_DETAIL)")


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
        query = text("select a.*, b.infoNo from lionsClub a left join voteClubaddinfo b on a.clubNo = b.clubNo and b.infoType='AINFO' where a.attrib not like :attpatt")
        result = await db.execute(query, {"attpatt": "%XXX%"})
        club_list = result.fetchall()
        return club_list
    except:
        raise HTTPException(status_code=500, detail="Database query failed(CLUBLIST)")


async def get_ranklist(db: AsyncSession):
    try:
        query = text("SELECT * FROM lionsRank WHERE attrib = :attpatt AND rankDiv IN ('DIST', 'CLUB') ORDER BY orderNo DESC")
        result = await db.execute(query, {"attpatt": "1000010000"})
        rank_list = result.fetchall()
        return rank_list
    except:
        raise HTTPException(status_code=500, detail="Database query failed(RANKLIST)")



async def get_circlelist(db: AsyncSession):
    try:
        query = text("select * from lionsCircle where attrib = :attpatt and circleType=:ctype")
        result = await db.execute(query, {"attpatt": "1000010000", "ctype": "VOTEC"})
        circle_list = result.fetchall()
        return circle_list
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(CIRCLELIST)")


async def get_contactlist(db: AsyncSession):
    try:
        query = text("select * from voteContact where attrib = :attpatt")
        result = await db.execute(query, {"attpatt": "1000010000"})
        contact_list = result.fetchall()
        return contact_list
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(CONTACTLIST)")


async def get_notelist(candtype: str, db: AsyncSession):
    try:
        query = text("select * from voteNote where attrib = :attpatt and noteType = :ntype")
        result = await db.execute(query, {"attpatt": "1000010000", "ntype": candtype})
        rows = result.mappings().all()
        note_list = []
        for row in rows:
            row_dict = dict(row)
            # datetime 객체를 JSON 직렬화가 가능한 문자열로 변환
            for key, value in row_dict.items():
                if isinstance(value, datetime):
                    row_dict[key] = value.strftime('%Y-%m-%d %H:%M:%S')
            note_list.append(row_dict)

        return note_list
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(NOTELIST)")


async def get_contactdtl(contactno:int,db: AsyncSession):
    try:
        query = text("select * from voteContact where contactNo = :contn")
        result = await db.execute(query, {"contn": contactno})
        contact_dtl = result.fetchone()
        return contact_dtl
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(CONTACTDETAIL)")


async def get_notedtl(noteno:int,db: AsyncSession):
    try:
        query = text("select * from voteNote where noteNo = :noten")
        result = await db.execute(query, {"noten": noteno})
        note_dtl = result.fetchone()
        return note_dtl
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Database query failed(NOTEDETAIL)")

@app.get("/sse/schedule")
async def sse_schedule(request: Request):
    q = hub.connect()
    async def gen():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                msg = await q.get()
                payload = json.dumps(jsonable_encoder(msg["data"]), ensure_ascii=False)
                # SSE 포맷
                yield f"event: {msg['event']}\n"
                yield f"data: {payload}\n\n"
        finally:
            hub.disconnect(q)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/favicon.ico")
async def favicon():
    return {"detail": "Favicon is served at /static/favicon.ico"}


@app.api_route("/", response_class=HTMLResponse, methods=["GET", "POST"])
async def login_form(request: Request):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/noname", status_code=303)
    return RedirectResponse(url="/success", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, next: str = Query(default="/success")):
    return templates.TemplateResponse("login/login.html", {"request": request, "next": next})


@app.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/success"),
    db: AsyncSession = Depends(get_db),
):
    query = text("""
        SELECT userNo, userName, userRole
        FROM voteUser
        WHERE userId = :username AND userPasswd = password(:password)
    """)
    result = await db.execute(query, {"username": username, "password": password})
    user = result.fetchone()

    if user is None:
        # 로그인 실패 시에도 next를 다시 넘겨줘야 화면에서 유지됨
        return templates.TemplateResponse(
            "login/login.html",
            {"request": request, "error": "Invalid credentials", "next": next},
            status_code=401,
        )

    query2 = text("""
        UPDATE voteUser
        SET loginStamp = :now, logoutStamp = NULL
        WHERE userNo = :userNo
    """)
    await db.execute(query2, {"now": datetime.now(), "userNo": user[0]})
    await db.commit()

    request.session["vote_user_No"] = user[0]
    request.session["vote_user_Name"] = user[1]
    request.session["vote_user_Role"] = user[2]

    # next가 외부 URL이면 오픈리다이렉트 위험 -> 내부 경로만 허용
    if not next.startswith("/"):
        next = "/success"

    return RedirectResponse(url=next, status_code=303)


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
        reserv_dict = {"reservNo": reservno, "reservFrom":'' , "visitCnt": ''}
        await hub.broadcast("reserv_created", reserv_dict)
        return JSONResponse({"canceled": True})
    except Exception as e:
        return JSONResponse({"canceled": False, "error": str(e)}, status_code=500)


@app.post("/reserv_arrv/{reservno}")
async def arrive_reservations(reservno: int, db: AsyncSession = Depends(get_db)):
    try:
        query = text("""
            update voteReserv
            set modDate = :now, attrib = :attr
            where reservNo = :reservno
        """)
        await db.execute(query, {
            "now": datetime.now(),
            "attr": "1111111111",
            "reservno": reservno,
        })
        await db.commit()
        reserv_dict = {"reservNo": reservno, "reservFrom":'' , "visitCnt": ''}
        await hub.broadcast("reserv_created", reserv_dict)
        return JSONResponse({"arrived": True})
    except Exception as e:
        return JSONResponse({"arrived": False, "error": str(e)}, status_code=500)


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
    # 이미지가 저장된 실제 폴더 경로 (프로젝트 구조에 맞게 수정 필요)
    hist_dir = "static/assets/hist"
    def get_images(prefix):
        if not os.path.exists(hist_dir):
            return []
        valid_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        files = [f for f in os.listdir(hist_dir) if f.startswith(prefix) and f.lower().endswith(valid_exts)]
        files.sort()
        return [f"/static/assets/hist/{f}" for f in files]
    h01_images = get_images("h1-")
    h02_images = get_images("h2-")
    h03_images = get_images("h3-")
    h04_images = get_images("h4-")
    h05_images = get_images("h5-")
    h06_images = get_images("h6-")
    h07_images = get_images("h7-")

    # 만약 폴더에 사진이 없을 경우를 대비한 더미 이미지 (테스트용)
    if not h01_images:
        h01_images = ["https://dummyimage.com/800x500/343a40/6c757d"]
    if not h02_images:
        h02_images = ["https://dummyimage.com/800x500/5c2a8a/ffffff"]
    if not h03_images:
        h03_images = ["https://dummyimage.com/800x500/5c2a8a/ffffff"]
    if not h04_images:
        h04_images = ["https://dummyimage.com/800x500/5c2a8a/ffffff"]
    if not h05_images:
        h05_images = ["https://dummyimage.com/800x500/5c2a8a/ffffff"]
    if not h06_images:
        h06_images = ["https://dummyimage.com/800x500/5c2a8a/ffffff"]
    if not h07_images:
        h07_images = ["https://dummyimage.com/800x500/5c2a8a/ffffff"]

    context = {
        "request": request,
        "h01_images": h01_images,
        "h02_images": h02_images,
        "h03_images": h03_images,
        "h04_images": h04_images,
        "h05_images": h05_images,
        "h06_images": h06_images,
        "h07_images": h07_images
    }
    return templates.TemplateResponse("history/projects.html", context)

@app.get("/success", response_class=HTMLResponse)
async def success(request: Request):
    return templates.TemplateResponse(
        "index/index.html", {"request": request, "session": dict(request.session)}
    )


@app.get("/noname", response_class=HTMLResponse)
async def success(request: Request):
    return templates.TemplateResponse(
        "index/index.html", {"request": request, "user_No": request.session.get("user_No")}
    )


@app.get("/view_visitors", response_class=HTMLResponse)
async def view_visitors(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino, db)
    return templates.TemplateResponse("view/template_candi.html", {"request": request, "session": dict(request.session), "reservations": reservs})


@app.get("/view_reservdtl/{reservno}", response_class=HTMLResponse)
async def view_visitors(request: Request,reservno:int ,db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    reserv_dtl = await get_reserv_dtl(reservno, db)
    cmembers = await get_clubmembers(reserv_dtl["clubNo"], db)
    visitors = await get_visitors(reservno, db)
    photo_dir = Path("static/img/event_photos")
    files = sorted(photo_dir.glob(f"{reservno}-*.jpg"))
    event_photos = [f"/static/img/event_photos/{p.name}" for p in files]
    return templates.TemplateResponse("view/reserv_dtl.html", {"request": request, "reserv": reserv_dtl, "visitors": visitors,"event_photos": event_photos, "cmembers": cmembers})


@app.get("/view_reservdtl_candi/{reservno}", response_class=HTMLResponse)
async def view_visitors(request: Request,reservno:int ,db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    candino = int(os.getenv("candiNo"))
    reserv_dtl = await get_reserv_dtl(reservno, db)
    circleno = reserv_dtl["circleNo"]
    clubno = reserv_dtl["clubNo"]
    cmembers = await get_clubmembers(reserv_dtl["clubNo"], db)
    if clubno :
        clubdtl = await get_club_dtl(clubno, db)
    if circleno :
        clubdtl = []
    visitors = await get_visitors(reservno, db)
    notes = await get_notelist("CANDI", db)
    photo_dir = Path("static/img/event_photos")
    files = sorted(photo_dir.glob(f"{reservno}-*.jpg"))
    event_photos = [f"/static/img/event_photos/{p.name}" for p in files]
    return templates.TemplateResponse("view/reserv_dtl_candi.html", {"request": request, "reserv": reserv_dtl, "visitors": visitors,"event_photos": event_photos, "clubdtl": clubdtl, "notes":notes, "cmembers":cmembers})


@app.get("/view_reservdtl_aide/{reservno}", response_class=HTMLResponse)
async def view_visitors(request: Request,reservno:int ,db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    candino = int(os.getenv("candiNo"))
    reserv_dtl = await get_reserv_dtl(reservno, db)
    circleno = reserv_dtl["circleNo"]
    clubno = reserv_dtl["clubNo"]
    if clubno :
        clubdtl = await get_club_dtl(clubno, db)
    if circleno :
        clubdtl = []
    visitors = await get_visitors(reservno, db)
    notes = await get_notelist("AIDE", db)
    photo_dir = Path("static/img/event_photos")
    files = sorted(photo_dir.glob(f"{reservno}-*.jpg"))
    event_photos = [f"/static/img/event_photos/{p.name}" for p in files]
    return templates.TemplateResponse("view/reserv_dtl_aide.html", {"request": request, "reserv": reserv_dtl, "visitors": visitors,"event_photos": event_photos, "clubdtl": clubdtl, "notes":notes})


@app.get("/view_reservsimple/{reservno}", response_class=HTMLResponse)
async def view_visitorssimple(request: Request,reservno:int ,db: AsyncSession = Depends(get_db)):
    reserv_dtl = await get_reserv_dtl(reservno, db)
    visitors = await get_visitors(reservno, db)
    return templates.TemplateResponse("view/reserv_simple.html", {"request": request, "reserv": reserv_dtl, "visitors": visitors})


@app.get("/viewer/candi_view", response_class=HTMLResponse)
async def view_candi(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    rows = await get_apireserv(db)
    result = []
    for row in rows:
        dt = row[4]
        reserv_from = dt.isoformat(timespec="minutes") if hasattr(dt, "isoformat") else str(dt)
        result.append({
            "reservNo": row[0],
            "reservFrom": reserv_from,  # "2026-03-10T09:00"
            "visitCnt": row[7],
            "reservMemo": row[8],
            "visitorName": (row[12] or row[13]) or "",
            "attrib": row[11],
        })
    return templates.TemplateResponse(
        "templete/candi_view.html",
        {"request": request, "reservs": result},
    )


@app.get("/viewer/aide_view", response_class=HTMLResponse)
async def view_aide(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    rows = await get_apireserv(db)
    result = []
    for row in rows:
        dt = row[4]
        reserv_from = dt.isoformat(timespec="minutes") if hasattr(dt, "isoformat") else str(dt)
        result.append({
            "reservNo": row[0],
            "reservFrom": reserv_from,  # "2026-03-10T09:00"
            "visitCnt": row[7],
            "reservMemo": row[8],
            "visitorName": (row[12] or row[13]) or "",
            "attrib": row[11],
        })
    return templates.TemplateResponse(
        "templete/aide_view.html",
        {"request": request, "reservs": result},
    )


@app.get("/viewer/history_view", response_class=HTMLResponse)
async def view_history(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino, db)
    return templates.TemplateResponse("templete/history_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/vision_view", response_class=HTMLResponse)
async def view_vision(request: Request, db: AsyncSession = Depends(get_db)):
    candino = int(os.getenv("candiNo"))
    reservs = await get_reservations(candino, db)
    return templates.TemplateResponse("templete/vision_view.html", {"request": request, "reservations": reservs})


@app.get("/viewer/schedule_today", response_class=HTMLResponse)
async def view_today(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    rows = await get_apireserv(db)
    result = []
    for row in rows:
        dt = row[4]
        reserv_from = dt.isoformat(timespec="minutes") if hasattr(dt, "isoformat") else str(dt)
        result.append({
            "reservNo": row[0],
            "reservFrom": reserv_from,   # "2026-03-10T09:00"
            "visitCnt": row[7],
            "reservMemo": row[8],
            "visitorName": (row[12] or row[13]) or "",
        })
    return templates.TemplateResponse(
        "templete/sched_today.html",
        {"request": request, "reservs": result},
    )


@app.get("/viewer/schedule_week", response_class=HTMLResponse)
async def view_week(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    rows = await get_apireserv(db)
    result = []
    for row in rows:
        dt = row[4]  # datetime일 가능성
        reserv_from = dt.isoformat(timespec="minutes") if hasattr(dt, "isoformat") else str(dt)
        result.append({
            "reservNo": row[0],
            "reservFrom": reserv_from,   # "2026-03-10T09:00"
            "visitCnt": row[7],
            "reservMemo": row[8],
            "visitorName": (row[12] or row[13]) or "",
            "attrib": row[11],
        })
    return templates.TemplateResponse(
        "templete/sched_week.html",
        {"request": request, "reservs": result},
    )


@app.post("/api/eventphotoupload/{eventNo}")
async def upload_event_photo(eventNo: int, photo: UploadFile = File(...)):
    if photo.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported content type: {photo.content_type}")
    ext = EXT_BY_CONTENT_TYPE.get(photo.content_type, "")
    if not ext:
        raise HTTPException(status_code=415, detail="Unsupported content type (no extension mapping)")
    idx = 1
    while True:
        filename = f"{eventNo}-{idx}{ext}"   # <- 하이픈을 항상 명시
        save_path = PHOTO_DIR / filename
        if not save_path.exists():
            break
        idx += 1
    try:
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    url_path = f"/static/img/event_photos/{filename}"
    return {"eventNo": eventNo, "filename": filename, "contentType": photo.content_type, "savedPath": str(save_path), "url": url_path}


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
        reserv_dict = {"reservNo": vr.reservNo, "reservFrom": vr.reservFrom, "visitCnt": vr.visitorCount}
        await hub.broadcast("reserv_created", reserv_dict)
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
        reserv_dict = {"reservNo": vr.reservNo, "reservFrom": vr.reservFrom, "visitCnt": vr.visitorCount}
        await hub.broadcast("reserv_created", reserv_dict)
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
        rows = await get_apireserv(db)
        result = [{"reservNo": row[0], "reservFrom": row[4], "visitCnt": row[7], "reservMemo": row[8], "visitorName": (row[12] or row[13]), "status": row[11]} for row in rows]
    except Exception as e:
        print(e)
        result = []
    finally:
        return {"reservs": result}


@app.get("/scribe01", response_class=HTMLResponse)
async def scribe01(
        request: Request,
        reservno: int = Query(...),
        photo: List[str] = Query(default=[]),  # 여러 개의 사진 URL을 리스트로 받음
        phrase: List[str] = Query(default=[]),  # 여러 개의 문구를 리스트로 받음
        db: AsyncSession = Depends(get_db),
):
    photo_data = []

    # 최대 2장까지만 처리
    for i in range(min(len(photo), 2)):
        p_url = photo[i]
        # phrase 리스트가 photo보다 짧을 경우를 대비한 안전 처리
        p_phrase = phrase[i] if i < len(phrase) else ""

        if not p_url.startswith("/static/"):
            p_url = "/static/img/event_photos/default.jpg"

        # 사진과 문구를 딕셔너리로 묶어서 저장
        photo_data.append({"url": p_url, "phrase": p_phrase})

    # 사진이 하나도 없을 경우 기본값
    if not photo_data:
        photo_data = [{"url": "/static/img/event_photos/default.jpg", "phrase": ""}]

    reserv = await get_reserv_dtl(reservno, db)

    return templates.TemplateResponse(
        "templete/scribe01.html",
        {
            "request": request,
            "photo_data": photo_data,  # photo_urls 대신 photo_data(딕셔너리 리스트) 전달
            "reserv": reserv
        },
    )


@app.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    return templates.TemplateResponse(
        "manage/contact.html", {"request": request}
    )


@app.api_route("/insert_contact/", methods=["POST"])  # GET은 불필요하므로 제거해도 무방합니다
async def insertcontact(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    doctitle = form_data.get("dtitle")
    docconts = form_data.get("dcontent")
    dwriter1 = form_data.get("dwriter1")
    dwriter2 = form_data.get("dwriter2")
    query = text(
        f"INSERT INTO voteContact (contactTitle, contactContent, writerRank, writerName) values (:doctitle,:docconts,:dwriter1,:dwriter2) ")
    await db.execute(query, {"doctitle": doctitle, "docconts": docconts,
                             "dwriter1": dwriter1, "dwriter2": dwriter2})
    await db.commit()
    return JSONResponse(content={"message": "성공적으로 저장되었습니다.", "redirect_url": "/"})

@app.api_route("/club_infoadd/{clubno}", methods=["POST"])  # GET은 불필요하므로 제거해도 무방합니다
async def insertinfo(request: Request,clubno ,db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    info = form_data.get("clubaddinfo")
    query = text(
        f"UPDATE voteClubaddinfo set attrib = :att , modDate = :nowt where clubNo = :clubno and infoType = :infotype ")
    await db.execute(query, {"att": "XXXUPXXXUP", "nowt": datetime.now(),"clubno":clubno,"infotype":"AINFO"})
    await db.commit()
    ql = text(f"INSERT INTO voteClubaddinfo (clubNo, infoContent) values (:clubno,:infoc)")
    await db.execute(ql, {"clubno": clubno, "infoc": info})
    await db.commit()
    return JSONResponse(content={"message": "성공적으로 저장되었습니다.", "redirect_url": "/manage_clubs"})

@app.api_route("/insert_note/", methods=["POST"])  # GET은 불필요하므로 제거해도 무방합니다
async def insertnote(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    doctitle = form_data.get("dtitle")
    docconts = form_data.get("dcontent")
    ntype = form_data.get("ntype")
    query = text(
        f"INSERT INTO voteNote (noteTitle, noteContents, noteType) values (:doctitle,:docconts,:ntype) ")
    await db.execute(query, {"doctitle": doctitle, "docconts": docconts,"ntype":ntype})
    await db.commit()
    return JSONResponse(content={"message": "성공적으로 저장되었습니다.", "redirect_url": "/"})


@app.api_route("/update_note/{noteno}", methods=["POST"])  # GET은 불필요하므로 제거해도 무방합니다
async def insertnote(request: Request,noteno:int ,db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    doctitle = form_data.get("dtitle")
    docconts = form_data.get("dcontent")
    ntype = form_data.get("ntype")
    rdir = ""
    query = text(
        f"UPDATE voteNote set noteTitle = :doctitle, noteContents = :docconts where noteNo = :noteno")
    await db.execute(query, {"doctitle": doctitle, "docconts": docconts,"noteno":noteno})
    await db.commit()
    if ntype == 'CANDI':
        rdir = "/notelist_candi"
    else:
        rdir = "/notelist_aide"
    return JSONResponse(content={"message": "성공적으로 저장되었습니다.", "redirect_url": rdir})


@app.api_route("/done_contact/{contactno}", methods=["POST"])
async def donecontact(request: Request,contactno:int ,db: AsyncSession = Depends(get_db)):
    query = text(
        f"UPDATE voteContact set attrib = :upd , modDate = :now where contactNo = :contactno ")
    await db.execute(query, {"upd": '1DONE1DONE', "now": datetime.now(), "contactno": contactno})
    await db.commit()
    return JSONResponse(content={"message": "성공적으로 저장되었습니다.", "redirect_url": "/contact_list"})


@app.api_route("/done_reserv/{reservno}", methods=["POST"])
async def donereserv(request: Request,reservno:int ,db: AsyncSession = Depends(get_db)):
    query = text(
        f"UPDATE voteReserv set attrib = :upd , modDate = :now where reservNo = :reservno ")
    await db.execute(query, {"upd": '1DONE1DONE', "now": datetime.now(), "reservno": reservno})
    await db.commit()
    return JSONResponse(content={"message": "성공적으로 저장되었습니다."})


@app.get("/contact_list", response_class=HTMLResponse)
async def contact_list(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    contacts = await get_contactlist(db)
    return templates.TemplateResponse(
        "manage/contact_list.html", {"request": request, "contacts": contacts}
    )


@app.get("/notelist_candi", response_class=HTMLResponse)
async def candinote_list(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    notes = await get_notelist("CANDI",db)
    return templates.TemplateResponse(
        "manage/candinote_list.html", {"request": request, "contacts": notes}
    )


@app.get("/notelist_aide", response_class=HTMLResponse)
async def aidenote_list(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    notes = await get_notelist("AIDE",db)
    return templates.TemplateResponse(
        "manage/aidenote_list.html", {"request": request, "notes": notes}
    )


@app.get("/newnote", response_class=HTMLResponse)
async def newnote(request: Request,ntype: Optional[str] = None):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    ntype = ntype or request.query_params.get("ntype")
    return templates.TemplateResponse("manage/newnote.html", {"request": request, "ntype": ntype}
    )


@app.post("/uploadmphoto/{memberno}")
async def upload_logoimage(request: Request, memberno: int, file: UploadFile = File(...),
                           db: AsyncSession = Depends(get_db)):
    try:
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File type not supported.")
        # 파일 읽기
        contents = await file.read()
        # 이미지 사이즈 조절
        contents = await resize_image_if_needed(contents, max_bytes=102400)
        # 이미지 저장
        await save_memberPhoto(contents, memberno)
        # 리다이렉트
        return RedirectResponse(f"/edit_member/{memberno}", status_code=303)
    except Exception as e:
        print(f"Error: {e}")
        return RedirectResponse(f"/edit_member/{memberno}", status_code=303)


@app.get("/contact_detail/{contactno}", response_class=HTMLResponse)
async def contact_dtl(request: Request, contactno:int, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    contact = await get_contactdtl(contactno, db)
    return templates.TemplateResponse(
        "manage/contact_detail.html", {"request": request, "contact": contact}
    )


@app.get("/note_detail/{noteno}", response_class=HTMLResponse)
async def note_dtl(request: Request, noteno:int, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    contact = await get_notedtl(noteno, db)
    return templates.TemplateResponse(
        "manage/note_detail.html", {"request": request, "notedtl": contact}
    )


@app.get("/manage_mst", response_class=HTMLResponse)
async def managemst(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("manage/manage_mster.html", {"request": request, "session": dict(request.session)})


@app.get("/manage_cmembers", response_class=HTMLResponse)
async def managecmembers(request: Request, clubno: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    clubs = await get_clublist(db)
    return templates.TemplateResponse("manage/manage_clubmembers.html", {
        "request": request,
        "session": dict(request.session),
        "clubs": clubs,
        "clubno": clubno
    })


@app.get("/manage_clubs", response_class=HTMLResponse)
async def manageclubs(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    clubs = await get_clublist(db)
    return templates.TemplateResponse("manage/manage_clubs.html", {
        "request": request,
        "session": dict(request.session),
        "clubs": clubs,
    })


@app.get("/new_member", response_class=HTMLResponse)
async def newmember(request: Request, club_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    clubs = await get_clublist(db)
    ranks = await get_ranklist(db)
    return templates.TemplateResponse("manage/new_member.html", {
        "request": request,
        "session": dict(request.session),
        "clubs": clubs,
        "ranks": ranks,
        "club_id": club_id
    })


@app.get("/edit_member/{memberno}", response_class=HTMLResponse)
async def newmember(request: Request, memberno: Optional[int] = None, club_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    clubs = await get_clublist(db)
    ranks = await get_ranklist(db)
    member = await get_memberdtl(memberno, db)
    return templates.TemplateResponse("manage/edit_member.html", {
        "request": request,
        "session": dict(request.session),
        "clubs": clubs,
        "ranks": ranks,
        "memberdtl": member,
        "club_id": club_id
    })


@app.get("/edit_club/{clubno}", response_class=HTMLResponse)
async def newmember(request: Request, clubno: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    if not request.session.get("vote_user_No"):
        return RedirectResponse(url="/login", status_code=303)
    clubdtl = await get_clubdtl(clubno, db)
    return templates.TemplateResponse("manage/edit_club.html", {
        "request": request,
        "session": dict(request.session), "clubdtl": clubdtl
    })


@app.api_route("/member_insert/", methods=["POST"])
async def insertcontact(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    membername = form_data.get("membername")
    clubno = form_data.get("memberclub")
    rankno = form_data.get("memberrank")
    query = text(
        f"INSERT INTO lionsMember (memberName, clubNo, rankNo) values (:mname,:mclub,:mrank) ")
    await db.execute(query, {"mname": membername, "mclub": clubno,
                             "mrank": rankno})
    await db.commit()
    return JSONResponse(content={"message": "성공적으로 저장되었습니다.", "redirect_url": f"/manage_cmembers?clubno={clubno}"})


@app.api_route("/member_update/{memberno}", methods=["POST"])
async def insertcontact(request: Request, memberno: int, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    membername = form_data.get("membername")
    clubno = form_data.get("memberclub")
    rankno = form_data.get("memberrank")
    query = text(
        f"UPDATE lionsMember SET memberName = :mname, clubNo = :mclub, rankNo = :mrank where memberNo = :memberno ")
    await db.execute(query, {"mname": membername, "mclub": clubno, "mrank": rankno, "memberno": memberno})
    await db.commit()
    return JSONResponse(content={"message": "성공적으로 저장되었습니다.", "redirect_url": f"/manage_cmembers?clubno={clubno}"})


@app.get("/api/clubmembers/{clubno}")
async def api_get_clubmembers(clubno: int, db: AsyncSession = Depends(get_db)):
    members = await get_clubmembers(clubno, db)
    result = []
    for m in members:
        result.append({
            "memberNo": m[0],
            "memberName": m[1],
            "rankNo": m[2],
            "rankTitlekor": m[3] if m[3] else "-",
            "clubNo": m[4]
        })
    return JSONResponse(content=result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
    )