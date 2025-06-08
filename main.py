from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import random
import string
from sqlalchemy import create_engine, text, select, func, exc
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from fastapi import Request
import requests

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
engine = create_engine(DATABASE_URL, fast_executemany=True, connect_args={"autocommit": True})

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

class MoveContentRequest(BaseModel):
    new_lab_id: int

class ReorderContentRequest(BaseModel):
    new_view_number: int

class ContentViewLog(BaseModel):
    training_key: str
    member_id: str
    lab_id: int
    content_id: int

@app.get("/")
async def read_root():
    return FileResponse("templates/index.html")

@app.post("/api/login")
async def login(data: LoginRequest):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT member_password, role FROM training_member WHERE training_key = :training_key AND member_id = :member_id"),
            {"training_key": data.training_key, "member_id": data.username}
        ).fetchone()
        if not result:
            raise HTTPException(status_code=400, detail="존재하지 않는 회원이거나 트레이닝 키가 잘못되었습니다.")
        if result[0] != data.password:
            raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")
        role = result[1]
    return {"message": "Login successful", "role": role}

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

@app.get("/admin")
async def admin_page():
    return FileResponse("templates/admin.html")

@app.get("/admin/lab")
async def lab_page():
    return FileResponse("templates/lab.html")

@app.get("/admin/lab_content")
async def lab_content_page():
    return FileResponse("templates/lab_content.html")

@app.get("/admin/user_analytics")
async def user_analytics_page():
    return FileResponse("templates/user_analytics.html")

@app.get("/portal/lab_content")
async def portal_lab_content_page():
    return FileResponse("templates/portal_lab_content.html")

@app.get("/api/admin/users")
async def get_users():
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT member_id, member_name, role, create_date FROM training_member ORDER BY create_date DESC")
        ).fetchall()
        users = [{"member_id": row[0], "member_name": row[1], "role": row[2], "create_date": row[3]} for row in result]
    return users

@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: str):
    with engine.connect() as conn:
        try:
            conn.execute(
                text("DELETE FROM training_member WHERE member_id = :member_id"),
                {"member_id": user_id}
            )
            conn.commit()
            return {"message": "User deleted successfully"}
        except SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")

@app.get("/api/admin/courses")
async def get_courses():
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT training_key, couse_name, couse_content, max_member, create_date, training_status FROM training ORDER BY create_date DESC")
        ).fetchall()
        courses = [
            {
                "training_key": row[0],
                "course_name": row[1],
                "course_content": row[2],
                "max_member": row[3],
                "create_date": row[4].strftime('%Y-%m-%d %H:%M') if row[4] else '',
                "training_status": row[5]
            }
            for row in result
        ]
    return courses

@app.get("/api/admin/courses/{training_key}")
async def get_course(training_key: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT training_key, couse_name, couse_content, max_member, create_date, training_status FROM training WHERE training_key = :key"),
            {"key": training_key}
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="과정을 찾을 수 없습니다.")
        return {
            "training_key": row[0],
            "course_name": row[1],
            "course_content": row[2],
            "max_member": row[3],
            "create_date": row[4].strftime('%Y-%m-%d %H:%M') if row[4] else '',
            "training_status": row[5]
        }

@app.post("/api/admin/courses")
async def add_course(data: dict = Body(...)):
    with engine.begin() as conn:
        now = datetime.now()
        date_str = now.strftime('%Y%m%d')
        # 일련번호 01~99까지 시도
        for seq in range(1, 100):
            training_key = f"{date_str}{seq:02d}"
            exists = conn.execute(
                text("SELECT 1 FROM training WHERE training_key = :training_key"),
                {"training_key": training_key}
            ).fetchone()
            if not exists:
                break
        else:
            raise HTTPException(status_code=500, detail="오늘은 더 이상 코스를 생성할 수 없습니다.")
        try:
            conn.execute(
                text("INSERT INTO training (training_key, couse_name, couse_content, max_member, create_date, training_status) VALUES (:training_key, :couse_name, :couse_content, :max_member, :create_date, :training_status)"),
                {
                    "training_key": training_key,
                    "couse_name": data.get("couse_name"),
                    "couse_content": data.get("couse_content"),
                    "max_member": data.get("max_member"),
                    "create_date": now,
                    "training_status": data.get("training_status")
                }
            )
        except exc.SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail=f"코스 추가 실패: {str(e)}")
    return {"message": "코스가 추가되었습니다."}

@app.put("/api/admin/courses/{training_key}")
async def update_course(training_key: str, data: dict = Body(...)):
    print(f"update_course called: training_key={training_key}, data={data}") # 디버깅을 위한 print
    with engine.begin() as conn:
        try:
            conn.execute(
                text("UPDATE training SET couse_name=:couse_name, couse_content=:couse_content, max_member=:max_member, training_status=:training_status WHERE training_key=:training_key"),
                {
                    "couse_name": data.get("course_name"),  # 'course_name' 키로 변경
                    "couse_content": data.get("course_content"), # 'course_content' 키로 변경
                    "max_member": int(data.get("max_member")), # int로 변환
                    "training_status": data.get("training_status"),
                    "training_key": training_key
                }
            )
        except exc.SQLAlchemyError as e:
            print(f"코스 수정 실패 (DB 오류): {e}") # 디버깅을 위한 print
            raise HTTPException(status_code=500, detail=f"코스 수정 실패: {str(e)}")
        except Exception as e:
            print(f"코스 수정 실패 (일반 오류): {e}") # 디버깅을 위한 print
            raise HTTPException(status_code=500, detail=f"코스 수정 중 예상치 못한 오류 발생: {str(e)}")
    return {"message": "코스가 수정되었습니다."}

@app.delete("/api/admin/courses/{training_key}")
async def delete_course(training_key: str):
    with engine.begin() as conn:
        try:
            conn.execute(
                text("DELETE FROM training WHERE training_key = :training_key"),
                {"training_key": training_key}
            )
        except exc.SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail=f"코스 삭제 실패: {str(e)}")
    return {"message": "코스가 삭제되었습니다."}

@app.get("/api/admin/labs")
async def get_labs(training_key: str = Query(...)):
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT
                    l.lab_id,
                    l.training_key,
                    l.lab_name,
                    l.lab_content,
                    l.lab_status,
                    l.create_date,
                    (SELECT COUNT(*) FROM training_lab_contents
                     WHERE training_key = l.training_key
                     AND lab_id = l.lab_id) as content_count
                FROM training_lab l
                WHERE l.training_key = :training_key
                ORDER BY l.lab_id
            """)
            result = conn.execute(query, {"training_key": training_key}).fetchall()
            labs = []
            for row in result:
                # 명시적으로 컬럼 이름을 사용하여 딕셔너리 생성
                lab_dict = {
                    "lab_id": row.lab_id,
                    "training_key": row.training_key,
                    "lab_name": row.lab_name,
                    "lab_content": row.lab_content,
                    "lab_status": row.lab_status,
                    "create_date": row.create_date.strftime('%Y-%m-%d %H:%M') if row.create_date else '',
                    "content_count": int(row.content_count)
                }
                labs.append(lab_dict)
            return labs
    except Exception as e:
        print(f"Error in get_labs: {e}") # 디버깅을 위한 에러 출력
        raise HTTPException(status_code=500, detail=f"랩 목록을 불러오는데 실패했습니다: {str(e)}")

@app.get("/api/admin/labs/{lab_id}")
async def get_lab(lab_id: int):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT lab_id, training_key, lab_name, lab_content, lab_status, create_date FROM training_lab WHERE lab_id = :lab_id"),
            {"lab_id": lab_id}
        ).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Lab not found")
        lab = {
            "lab_id": result[0],
            "training_key": result[1],
            "lab_name": result[2],
            "lab_content": result[3],
            "lab_status": result[4],
            "create_date": result[5].strftime('%Y-%m-%d %H:%M') if result[5] else ''
        }
        return lab

@app.post("/api/admin/labs")
async def add_lab(data: dict = Body(...)):
    with engine.begin() as conn:
        # training_key별로 lab_id는 1부터 시작하는 일련번호
        result = conn.execute(
            text("SELECT MAX(lab_id) FROM training_lab WHERE training_key = :training_key"),
            {"training_key": data.get("training_key")}
        ).fetchone()
        next_lab_id = 1 if result[0] is None else int(result[0]) + 1
        now = datetime.now()
        try:
            conn.execute(
                text("INSERT INTO training_lab (lab_id, training_key, lab_name, lab_content, lab_status, create_date) VALUES (:lab_id, :training_key, :lab_name, :lab_content, :lab_status, :create_date)"),
                {
                    "lab_id": next_lab_id,
                    "training_key": data.get("training_key"),
                    "lab_name": data.get("lab_name"),
                    "lab_content": data.get("lab_content"),
                    "lab_status": data.get("lab_status"),
                    "create_date": now
                }
            )
        except exc.SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail=f"랩 추가 실패: {str(e)}")
    return {"message": "랩이 추가되었습니다."}

@app.put("/api/admin/labs/{lab_id}")
async def update_lab(lab_id: int, data: dict = Body(...)):
    print(f"update_lab called: lab_id={lab_id}, data={data}") # 디버깅을 위한 print
    with engine.begin() as conn:
        try:
            conn.execute(
                text("UPDATE training_lab SET lab_name=:lab_name, lab_content=:lab_content, lab_status=:lab_status WHERE lab_id=:lab_id AND training_key=:training_key"),
                {
                    "lab_name": data.get("lab_name"),
                    "lab_content": data.get("lab_content"),
                    "lab_status": data.get("lab_status"),
                    "lab_id": lab_id,
                    "training_key": data.get("training_key")
                }
            )
        except exc.SQLAlchemyError as e:
            print(f"랩 수정 실패 (DB 오류): {e}") # 디버깅을 위한 print
            raise HTTPException(status_code=500, detail=f"랩 수정 실패: {str(e)}")
        except Exception as e:
            print(f"랩 수정 실패 (일반 오류): {e}") # 디버깅을 위한 print
            raise HTTPException(status_code=500, detail=f"랩 수정 중 예상치 못한 오류 발생: {str(e)}")
    return {"message": "랩이 수정되었습니다."}

@app.delete("/api/admin/labs/{lab_id}")
async def delete_lab(lab_id: int):
    with engine.begin() as conn:
        try:
            conn.execute(
                text("DELETE FROM training_lab WHERE lab_id = :lab_id"),
                {"lab_id": lab_id}
            )
        except exc.SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail=f"랩 삭제 실패: {str(e)}")
    return {"message": "랩이 삭제되었습니다."}

@app.get("/api/portal-info")
async def portal_info(request: Request):
    member_id = request.query_params.get("member_id")
    training_key = request.query_params.get("training_key")
    if not member_id or not training_key:
        raise HTTPException(status_code=400, detail="member_id 및 training_key가 필요합니다.")
    
    with engine.connect() as conn:
        # 사용자 정보 확인 및 member_name 조회
        member_result = conn.execute(
            text("SELECT member_name FROM training_member WHERE training_key = :training_key AND member_id = :member_id"),
            {"training_key": training_key, "member_id": member_id}
        ).fetchone()
        if not member_result:
            raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다.")
        member_name = member_result[0]

        # 과정명 및 상태 조회
        course_row = conn.execute(
            text("SELECT couse_name, training_status FROM training WHERE training_key = :key"),
            {"key": training_key}
        ).fetchone()
        
        course_name = course_row[0] if course_row else None
        course_status = course_row[1] if course_row else None

        # 랩 목록 조회
        labs_result = conn.execute(
            text("SELECT lab_id, lab_name, lab_content, lab_status, create_date FROM training_lab WHERE training_key = :key ORDER BY lab_id ASC"),
            {"key": training_key}
        ).fetchall()

        lab_list = []
        for r in labs_result:
            lab_list.append({
                "lab_id": r[0],
                "lab_name": r[1],
                "lab_content": r[2],
                "lab_status": r[3],
                "create_date": r[4].strftime('%Y-%m-%d %H:%M') if r[4] else ''
            })

    return {
        "member_id": member_id,
        "training_key": training_key,
        "member_name": member_name,
        "course_name": course_name,
        "course_status": course_status,
        "labs": lab_list
    }

@app.get("/api/admin/lab_user_counts")
async def get_lab_user_counts(training_key: str = Query(...)):
    try:
        with engine.connect() as conn:
            # 각 랩별 총 사용자 수 (training_member 테이블의 member_id 기준)
            # 실제로는 training_member 테이블에서 training_key에 해당하는 멤버만 카운트하는 것이 맞을 수 있음
            # 여기서는 training_lab_log에 기록된 사용자를 기준으로 랩별 사용자 수를 계산
            query = text("""
                SELECT 
                    tl.lab_id,
                    tl.lab_name,
                    COUNT(DISTINCT tll.member_key) AS user_count
                FROM training_lab tl
                LEFT JOIN training_lab_log tll ON tl.lab_id = tll.lab_id AND tl.training_key = tll.training_key
                WHERE tl.training_key = :training_key
                GROUP BY tl.lab_id, tl.lab_name
                ORDER BY tl.lab_id
            """)
            result = conn.execute(query, {"training_key": training_key}).fetchall()

            lab_counts = []
            for row in result:
                lab_counts.append({
                    "lab_id": row.lab_id,
                    "lab_name": row.lab_name,
                    "user_count": row.user_count
                })
            return lab_counts
    except SQLAlchemyError as e:
        print(f"[ERROR] Error fetching lab user counts: {e}")
        raise HTTPException(status_code=500, detail=f"랩별 사용자 수를 불러오는데 실패했습니다: {str(e)}")

@app.get("/api/admin/user_content_progress")
async def get_user_content_progress(
    training_key: str = Query(...),
    lab_id: int = Query(...)
):
    try:
        with engine.connect() as conn:
            # 1. 해당 랩의 모든 콘텐츠 (view_number 순서대로)
            contents_query = text("""
                SELECT content_id, lab_content_subject
                FROM training_lab_contents
                WHERE training_key = :training_key AND lab_id = :lab_id
                ORDER BY view_number ASC
            """)
            all_contents = conn.execute(contents_query, {"training_key": training_key, "lab_id": lab_id}).fetchall()
            
            contents_list = []
            for c in all_contents:
                contents_list.append({"content_id": c.content_id, "lab_content_subject": c.lab_content_subject})

            # 2. 해당 랩에 접근한 모든 사용자
            users_query = text("""
                SELECT DISTINCT tm.member_key, tm.member_id, tm.member_name
                FROM training_member tm
                JOIN training_lab_log tll ON tm.member_key = tll.member_key AND tm.training_key = tll.training_key
                WHERE tm.training_key = :training_key AND tll.lab_id = :lab_id
                ORDER BY tm.member_key ASC
            """)
            all_users = conn.execute(users_query, {"training_key": training_key, "lab_id": lab_id}).fetchall()

            users_list = []
            for u in all_users:
                # 각 사용자가 해당 랩의 어떤 콘텐츠를 조회했는지 가져오기
                viewed_contents_query = text("""
                    SELECT DISTINCT content_id
                    FROM training_lab_log
                    WHERE training_key = :training_key
                    AND member_key = :member_key
                    AND lab_id = :lab_id
                """)
                viewed_contents = conn.execute(viewed_contents_query, {
                    "training_key": training_key,
                    "member_key": u.member_key,
                    "lab_id": lab_id
                }).fetchall()
                
                users_list.append({
                    "member_key": u.member_key,
                    "member_id": u.member_id,
                    "member_name": u.member_name,
                    "viewed_contents": [vc.content_id for vc in viewed_contents]
                })
            
            return {"users": users_list, "contents": contents_list}
    except SQLAlchemyError as e:
        print(f"[ERROR] Error fetching user content progress: {e}")
        raise HTTPException(status_code=500, detail=f"사용자 진도 데이터를 불러오는데 실패했습니다: {str(e)}")

@app.post("/api/portal/log_content_view")
async def log_content_view(log: ContentViewLog):
    with engine.begin() as conn:
        try:
            # member_id로 member_key 조회
            member_result = conn.execute(
                text("SELECT member_key FROM training_member WHERE training_key = :training_key AND member_id = :member_id"),
                {"training_key": log.training_key, "member_id": log.member_id}
            ).fetchone()

            if not member_result:
                raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
            
            member_key = member_result[0]

            # 로그 기록이 이미 존재하는지 확인
            existing_log = conn.execute(
                text("SELECT 1 FROM training_lab_log WHERE training_key = :training_key AND member_key = :member_key AND lab_id = :lab_id AND content_id = :content_id"),
                {
                    "training_key": log.training_key,
                    "member_key": member_key,
                    "lab_id": log.lab_id,
                    "content_id": log.content_id
                }
            ).fetchone()

            if existing_log:
                print(f"[DEBUG] 콘텐츠 조회 기록 이미 존재: training_key={log.training_key}, member_key={member_key}, lab_id={log.lab_id}, content_id={log.content_id}")
                return {"message": "Content view already logged"}

            # 로그 삽입 전 디버그 출력
            print(f"[DEBUG] Inserting log: training_key={log.training_key}, member_key={member_key}, lab_id={log.lab_id}, content_id={log.content_id}, create_date={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 로그 기록
            conn.execute(
                text("INSERT INTO training_lab_log (training_key, member_key, lab_id, content_id, create_date) VALUES (:training_key, :member_key, :lab_id, :content_id, :create_date)"),
                {
                    "training_key": log.training_key,
                    "member_key": member_key,
                    "lab_id": log.lab_id,
                    "content_id": log.content_id,
                    "create_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            )
            print("[DEBUG] Content view log inserted successfully.")
            return {"message": "Content view logged successfully"}
        except SQLAlchemyError as e:
            print(f"[ERROR] SQLAlchemy Error during content view logging: {e}")
            raise HTTPException(status_code=500, detail=f"콘텐츠 조회 기록 실패: {str(e)}")

@app.get("/api/admin/lab_contents")
async def get_lab_contents(training_key: str = Query(...), lab_id: int = Query(...)):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT training_key, lab_id, content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date FROM training_lab_contents WHERE training_key = :training_key AND lab_id = :lab_id ORDER BY content_id ASC"),
            {"training_key": training_key, "lab_id": lab_id}
        ).fetchall()
        contents = [
            {
                "training_key": row[0],
                "lab_id": row[1],
                "content_id": row[2],
                "view_number": row[3],
                "lab_content_subject": row[4],
                "lab_content": row[5],
                "lab_content_type": row[6],
                "lab_content_status": row[7],
                "lab_content_create_date": row[8].strftime('%Y-%m-%d %H:%M') if row[8] else ''
            }
            for row in result
        ]
    return contents

@app.get("/api/admin/lab_contents/{content_id}")
async def get_lab_content(content_id: int, training_key: str = Query(...), lab_id: int = Query(...)):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date FROM training_lab_contents WHERE training_key = :training_key AND lab_id = :lab_id AND content_id = :content_id"),
            {"training_key": training_key, "lab_id": lab_id, "content_id": content_id}
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다.")
        return {
            "content_id": row[0],
            "view_number": row[1],
            "lab_content_subject": row[2],
            "lab_content": row[3],
            "lab_content_type": row[4],
            "lab_content_status": row[5],
            "lab_content_create_date": row[6].strftime('%Y-%m-%d %H:%M') if row[6] else ''
        }

@app.post("/api/admin/lab_contents")
async def add_lab_content(data: dict = Body(...)):
    with engine.begin() as conn:
        # content_id는 lab별로 1부터 시작하는 일련번호
        result_content_id = conn.execute(
            text("SELECT MAX(content_id) FROM training_lab_contents WHERE training_key = :training_key AND lab_id = :lab_id"),
            {"training_key": data.get("training_key"), "lab_id": data.get("lab_id")}
        ).fetchone()
        next_content_id = 1 if result_content_id[0] is None else int(result_content_id[0]) + 1

        # view_number는 해당 lab 내에서 MAX(view_number) + 1로 설정
        result_view_number = conn.execute(
            text("SELECT MAX(view_number) FROM training_lab_contents WHERE training_key = :training_key AND lab_id = :lab_id"),
            {"training_key": data.get("training_key"), "lab_id": data.get("lab_id")}
        ).fetchone()
        next_view_number = 1 if result_view_number[0] is None else int(result_view_number[0]) + 1

        now = datetime.now()
        try:
            conn.execute(
                text("INSERT INTO training_lab_contents (training_key, lab_id, content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date) VALUES (:training_key, :lab_id, :content_id, :view_number, :lab_content_subject, :lab_content, :lab_content_type, :lab_content_status, :lab_content_create_date)"),
                {
                    "training_key": data.get("training_key"),
                    "lab_id": data.get("lab_id"),
                    "content_id": next_content_id,
                    "view_number": next_view_number,  # 수정: view_number를 MAX(view_number) + 1로 설정
                    "lab_content_subject": data.get("lab_content_subject"),
                    "lab_content": data.get("lab_content"),
                    "lab_content_type": data.get("lab_content_type"),
                    "lab_content_status": data.get("lab_content_status"),
                    "lab_content_create_date": now
                }
            )
        except exc.SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail=f"콘텐츠 추가 실패: {str(e)}")
    return {"message": "콘텐츠가 추가되었습니다."}

@app.put("/api/admin/lab_contents/{content_id}")
async def update_lab_content(content_id: int, data: dict = Body(...)):
    with engine.begin() as conn:
        try:
            conn.execute(
                text("UPDATE training_lab_contents SET lab_content_subject=:lab_content_subject, lab_content=:lab_content, lab_content_status=:lab_content_status, lab_content_type=:lab_content_type WHERE training_key=:training_key AND lab_id=:lab_id AND content_id=:content_id"),
                {
                    "lab_content_subject": data.get("lab_content_subject"),
                    "lab_content": data.get("lab_content"),
                    "lab_content_status": data.get("lab_content_status"),
                    "lab_content_type": data.get("lab_content_type"),
                    "training_key": data.get("training_key"),
                    "lab_id": data.get("lab_id"),
                    "content_id": content_id
                }
            )
        except exc.SQLAlchemyError as e:
            print(f"콘텐츠 수정 실패 (DB 오류): {e}") # 디버깅을 위한 print
            raise HTTPException(status_code=500, detail=f"콘텐츠 수정 실패: {str(e)}")
        except Exception as e:
            print(f"콘텐츠 수정 실패 (일반 오류): {e}") # 디버깅을 위한 print
            raise HTTPException(status_code=500, detail=f"콘텐츠 수정 중 예상치 못한 오류 발생: {str(e)}")
    return {"message": "콘텐츠가 수정되었습니다."}

@app.delete("/api/admin/lab_contents/{content_id}")
async def delete_lab_content(content_id: int, training_key: str = Query(...), lab_id: int = Query(...)):
    with engine.begin() as conn:
        try:
            conn.execute(
                text("DELETE FROM training_lab_contents WHERE training_key = :training_key AND lab_id = :lab_id AND content_id = :content_id"),
                {"training_key": training_key, "lab_id": lab_id, "content_id": content_id}
            )
        except exc.SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail=f"콘텐츠 삭제 실패: {str(e)}")
    return {"message": "콘텐츠가 삭제되었습니다."}

@app.put("/api/admin/lab_contents/{content_id}/status")
async def update_lab_content_status(
    content_id: int,
    training_key: str = Query(...),
    lab_id: int = Query(...),
    new_status: int = Body(..., embed=True)
):
    with engine.begin() as conn:
        try:
            conn.execute(
                text("UPDATE training_lab_contents SET lab_content_status=:new_status WHERE training_key=:training_key AND lab_id=:lab_id AND content_id=:content_id"),
                {
                    "new_status": new_status,
                    "training_key": training_key,
                    "lab_id": lab_id,
                    "content_id": content_id
                }
            )
        except exc.SQLAlchemyError as e:
            print(f"콘텐츠 상태 업데이트 실패 (DB 오류): {e}")
            raise HTTPException(status_code=500, detail=f"콘텐츠 상태 업데이트 실패: {str(e)}")
        except Exception as e:
            print(f"콘텐츠 상태 업데이트 실패 (일반 오류): {e}")
            raise HTTPException(status_code=500, detail=f"콘텐츠 상태 업데이트 중 예상치 못한 오류 발생: {str(e)}")
    return {"message": "콘텐츠 상태가 성공적으로 업데이트되었습니다."}

@app.put("/api/admin/lab_contents/{content_id}/move")
async def move_lab_content(content_id: int, request: MoveContentRequest, training_key: str = Query(...)):
    print(f"move_lab_content called: content_id={content_id}, training_key={training_key}, new_lab_id={request.new_lab_id}")
    try:
        new_lab_id = request.new_lab_id
        with engine.begin() as conn:
            # 1. 현재 콘텐츠 정보 조회
            query = text("""
                SELECT training_key, lab_id 
                FROM training_lab_contents 
                WHERE content_id = :content_id
                AND training_key = :training_key
            """)
            result = conn.execute(query, {
                "content_id": content_id,
                "training_key": training_key
            }).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다.")
            
            # 2. 새로운 랩이 같은 과정에 속하는지 확인
            query = text("""
                SELECT COUNT(*) 
                FROM training_lab 
                WHERE training_key = :training_key 
                AND lab_id = :lab_id
            """)
            result = conn.execute(query, {
                "training_key": training_key,
                "lab_id": new_lab_id
            })
            if result.scalar() == 0:
                raise HTTPException(status_code=400, detail="해당 랩이 과정에 존재하지 않습니다.")
            
            # 3. 콘텐츠 이동
            query = text("""
                UPDATE training_lab_contents 
                SET lab_id = :new_lab_id 
                WHERE content_id = :content_id
                AND training_key = :training_key
            """)
            conn.execute(query, {
                "content_id": content_id,
                "new_lab_id": new_lab_id,
                "training_key": training_key
            })
            return {"message": "콘텐츠가 성공적으로 이동되었습니다."}
    except HTTPException as he:
        raise he
    except SQLAlchemyError as e:
        print(f"데이터베이스 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        print(f"예상치 못한 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"콘텐츠 이동 중 오류가 발생했습니다: {str(e)}")

@app.put("/api/admin/lab_contents/{content_id}/reorder")
async def update_lab_content_order(
    content_id: int,
    training_key: str = Query(...),
    lab_id: int = Query(...),
    request_body: ReorderContentRequest = Body(...)
):
    new_view_number = request_body.new_view_number
    
    try:
        with engine.begin() as conn:
            # 1. Get current view_number of the target content
            current_content_result = conn.execute(
                text("SELECT view_number FROM training_lab_contents WHERE training_key = :training_key AND lab_id = :lab_id AND content_id = :content_id"),
                {"training_key": training_key, "lab_id": lab_id, "content_id": content_id}
            ).fetchone()

            if not current_content_result:
                raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다.")
            
            old_view_number = current_content_result.view_number

            # 2. Get the total number of contents in the current lab
            total_count_result = conn.execute(
                text("SELECT COUNT(*) FROM training_lab_contents WHERE training_key = :training_key AND lab_id = :lab_id"),
                {"training_key": training_key, "lab_id": lab_id}
            ).fetchone()
            
            raw_total_content_count = total_count_result[0]
            total_content_count = raw_total_content_count if raw_total_content_count is not None else 0

            # For validation, the effective max_view_number should be the total count of items.
            # Ensure it's at least 1, even if the lab is empty (though content_id exists, so count is at least 1).
            effective_max_view_number_for_validation = max(1, total_content_count)

            print(f"[DEBUG] raw_total_content_count: {raw_total_content_count}, total_content_count (after null check): {total_content_count}")
            print(f"[DEBUG] content_id: {content_id}, old_view_number: {old_view_number}, effective_max_view_number_for_validation: {effective_max_view_number_for_validation}, new_view_number: {new_view_number}")

            if new_view_number < 1 or new_view_number > effective_max_view_number_for_validation:
                raise HTTPException(status_code=400, detail=f"유효하지 않은 순서 번호입니다. 1에서 {effective_max_view_number_for_validation} 사이의 값을 입력해주세요.")

            if old_view_number == new_view_number:
                return {"message": "콘텐츠 순서가 변경되지 않았습니다."}

            # Reordering logic
            if old_view_number == 0: # Case: Content had an invalid view_number, now assigning a valid one
                # Shift all items from new_view_number and up to make space
                conn.execute(
                    text("""
                        UPDATE training_lab_contents
                        SET view_number = view_number + 1
                        WHERE training_key = :training_key
                        AND lab_id = :lab_id
                        AND view_number >= :new_view_number
                    """),
                    {
                        "training_key": training_key,
                        "lab_id": lab_id,
                        "new_view_number": new_view_number
                    }
                )
            elif new_view_number < old_view_number: # Moving item up in the sequence
                # Shift items with view_number between new_view_number and old_view_number (exclusive of old_view_number) up by 1
                conn.execute(
                    text("""
                        UPDATE training_lab_contents
                        SET view_number = view_number + 1
                        WHERE training_key = :training_key
                        AND lab_id = :lab_id
                        AND view_number >= :new_view_number
                        AND view_number < :old_view_number
                    """),
                    {
                        "training_key": training_key,
                        "lab_id": lab_id,
                        "new_view_number": new_view_number,
                        "old_view_number": old_view_number
                    }
                )
            else: # new_view_number > old_view_number - Moving item down in the sequence
                # Shift items with view_number between old_view_number (exclusive) and new_view_number (inclusive) down by 1
                conn.execute(
                    text("""
                        UPDATE training_lab_contents
                        SET view_number = view_number - 1
                        WHERE training_key = :training_key
                        AND lab_id = :lab_id
                        AND view_number <= :new_view_number
                        AND view_number > :old_view_number
                    """),
                    {
                        "training_key": training_key,
                        "lab_id": lab_id,
                        "new_view_number": new_view_number,
                        "old_view_number": old_view_number
                    }
                )
            
            # Update the target content's view_number to its new position
            conn.execute(
                text("""
                    UPDATE training_lab_contents
                    SET view_number = :new_view_number
                    WHERE training_key = :training_key
                    AND lab_id = :lab_id
                    AND content_id = :content_id
                """),
                {
                    "training_key": training_key,
                    "lab_id": lab_id,
                    "content_id": content_id,
                    "new_view_number": new_view_number
                }
            )
            return {"message": "콘텐츠 순서가 성공적으로 업데이트되었습니다."}
    except HTTPException as he:
        raise he
    except SQLAlchemyError as e:
        print(f"데이터베이스 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        print(f"예상치 못한 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"콘텐츠 순서 변경 중 오류가 발생했습니다: {str(e)}")

@app.get("/api/proxy-markdown")
async def proxy_markdown(url: str):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return HTMLResponse(content=resp.text, status_code=200)
    except Exception as e:
        return HTMLResponse(content=f"URL에서 마크다운을 불러올 수 없습니다.\n{e}", status_code=400)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 