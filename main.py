from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn
import random
import string
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from fastapi import Request

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 제공 설정
app.mount("/static", StaticFiles(directory="static"), name="static")

# Azure SQL 접속 정보 (SQLAlchemy)
DB_SERVER = 'helloaihtc.database.windows.net'
DB_NAME = 'HTCdb'
DB_USER = 'winkey'
DB_PASSWORD = '!Korea10041004'
DB_DRIVER = 'ODBC Driver 17 for SQL Server'

# SQLAlchemy 엔진 생성
DATABASE_URL = f"mssql+pyodbc://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:1433/{DB_NAME}?driver={DB_DRIVER.replace(' ', '+')}"
engine = create_engine(DATABASE_URL, fast_executemany=True)

class UserLogin(BaseModel):
    username: str
    password: str

class TrainingKeyOnly(BaseModel):
    training_key: str

class RegisterMember(BaseModel):
    training_key: str
    member_key: int
    member_id: str
    member_name: str
    member_password: str

class LoginRequest(BaseModel):
    training_key: str
    username: str
    password: str

class RegisterMemberSimple(BaseModel):
    member_name: str
    member_password: str

class RegisterMemberWithKey(BaseModel):
    training_key: str
    member_name: str
    member_password: str

@app.get("/")
async def read_root():
    return FileResponse("templates/index.html")

@app.post("/api/login")
async def login(data: LoginRequest):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT member_password FROM training_member WHERE training_key = :training_key AND member_id = :member_id"),
            {"training_key": data.training_key, "member_id": data.username}
        ).fetchone()
        if not result:
            raise HTTPException(status_code=400, detail="존재하지 않는 회원이거나 트레이닝 키가 잘못되었습니다.")
        if result[0] != data.password:
            raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")
    return {"message": "Login successful"}

@app.post("/api/check-training-key")
async def check_training_key(data: TrainingKeyOnly):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT training_key FROM training WHERE training_key = :key"),
            {"key": data.training_key}
        ).fetchone()
        if not result:
            raise HTTPException(status_code=400, detail="트레이닝 키가 잘못되었습니다. 다시 한번 확인해 주세요")
    return {"message": "OK"}

@app.post("/api/next-member-key")
async def next_member_key(data: TrainingKeyOnly):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT MAX(member_key) FROM training_member WHERE training_key = :key"),
            {"key": data.training_key}
        ).fetchone()
        next_key = 1 if result[0] is None else int(result[0]) + 1
    return {"next_member_key": next_key}

@app.post("/api/register")
async def register_with_key(member: RegisterMemberWithKey):
    # 트레이닝 키 유효성 검사
    with engine.begin() as conn:
        valid_key = conn.execute(
            text("SELECT 1 FROM training WHERE training_key = :key"),
            {"key": member.training_key}
        ).fetchone()
        if not valid_key:
            raise HTTPException(status_code=400, detail="잘못된 트레이닝 키입니다.")
        # 다음 member_key 구하기
        result = conn.execute(
            text("SELECT MAX(member_key) FROM training_member WHERE training_key = :key"),
            {"key": member.training_key}
        ).fetchone()
        next_key = 1 if result[0] is None else int(result[0]) + 1
        member_id = f"labuser{next_key}"
        # 중복 체크
        result2 = conn.execute(
            text("SELECT 1 FROM training_member WHERE training_key = :key AND member_key = :mkey"),
            {"key": member.training_key, "mkey": next_key}
        ).fetchone()
        if result2:
            raise HTTPException(status_code=400, detail="이미 존재하는 회원 번호입니다.")
        # 회원 등록
        try:
            conn.execute(
                text("INSERT INTO training_member (member_key, training_key, member_id, member_name, member_password, role, create_date) VALUES (:member_key, :training_key, :member_id, :member_name, :member_password, :role, :create_date)"),
                {
                    "member_key": next_key,
                    "training_key": member.training_key,
                    "member_id": member_id,
                    "member_name": member.member_name,
                    "member_password": member.member_password,
                    "role": 10,
                    "create_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            )
        except SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail=f"회원 생성 실패: {str(e)}")
    return {"message": "Registration successful", "member_id": member_id}

@app.get("/register")
async def register_page():
    return FileResponse("templates/register.html")

@app.get("/portal")
async def portal_page():
    return FileResponse("templates/portal.html")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 