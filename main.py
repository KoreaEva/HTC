
from fastapi import FastAPI, HTTPException, Body, Query, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import pymysql
import requests
from datetime import datetime
from dotenv import load_dotenv
import os
import hashlib

load_dotenv()

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
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# MySQL 접속 정보
MYSQL_HOST = os.getenv('MYSQL_HOST', 'helloaibase-mysql-01.mysql.database.azure.com')
MYSQL_USER = os.getenv('MYSQL_USER', 'winkey')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '!Korea10041004')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'helloaibasedb')

def get_mysql_conn():
    try:
        print(f"[DEBUG] MySQL 연결 시도: {MYSQL_HOST}, {MYSQL_USER}, {MYSQL_DATABASE}")
        conn = pymysql.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=30,
            ssl={'ssl': {}}
        )
        print(f"[DEBUG] MySQL 연결 성공!")
        return conn
    except Exception as e:
        print(f"[ERROR] MySQL 연결 실패: {str(e)}")
        raise e

@app.get("/")
async def read_root():
    return FileResponse("templates/index.html")

@app.get("/training-portal")
async def training_portal():
    return FileResponse("templates/training_portal.html")

@app.get("/test-db")
async def test_db():
    """데이터베이스 연결 및 데이터 확인용 테스트 엔드포인트"""
    try:
        conn = get_mysql_conn()
        with conn.cursor() as cursor:
            # 테이블 존재 확인
            cursor.execute("SHOW TABLES LIKE 'event_forum'")
            table_exists = cursor.fetchone()
            if not table_exists:
                return {"error": "event_forum 테이블이 존재하지 않습니다"}
            
            # 전체 데이터 개수 확인
            cursor.execute("SELECT COUNT(*) as count FROM event_forum")
            total_count = cursor.fetchone()
            
            # 2025년 1월 데이터 개수 확인
            cursor.execute("SELECT COUNT(*) as count FROM event_forum WHERE YEAR(year) = 2025 AND MONTH(year) = 1")
            jan_2025_count = cursor.fetchone()
            
            # 샘플 데이터 조회
            cursor.execute("SELECT id, year, job_title, status FROM event_forum LIMIT 5")
            samples = cursor.fetchall()
            
            return {
                "database_connection": "성공",
                "table_exists": "예",
                "total_records": total_count['count'] if total_count else 0,
                "jan_2025_records": jan_2025_count['count'] if jan_2025_count else 0,
                "sample_data": samples
            }
    except Exception as e:
        return {"error": f"데이터베이스 오류: {str(e)}"}
    finally:
        if 'conn' in locals():
            conn.close()

# 일정 조회 API: /api/events
@app.get("/api/events")
async def get_events(year: int = None, month: int = None):
    print(f"[DEBUG] API 호출: year={year}, month={month}")
    try:
        conn = get_mysql_conn()
        print(f"[DEBUG] MySQL 연결 성공")
    except Exception as e:
        print(f"[ERROR] MySQL 연결 실패: {e}")
        raise HTTPException(status_code=500, detail=f"데이터베이스 연결 실패: {str(e)}")
    
    try:
        with conn.cursor() as cursor:
            # 전체 데이터 조회 (연도와 월이 지정되지 않은 경우)
            # 특정 연도와 월의 데이터만 조회 (날짜 범위로 조회)
            start_date = f"{year:04d}-{month:02d}-01"
            if month == 12:
                end_date = f"{year+1:04d}-01-01"
            else:
                end_date = f"{year:04d}-{month+1:02d}-01"
            
            sql = """
                SELECT id,
                        year,
                        job_title,
                        status,
                        start_time,
                        end_time,
                        location,
                        partner_company,
                        is_public,
                        client,
                        description
                FROM event_forum
                WHERE DATE(year) >= %s AND DATE(year) < %s
                ORDER BY year ASC, start_time ASC
            """
            cursor.execute(sql, (start_date, end_date))
            rows = cursor.fetchall()
            print(f"[DEBUG] 조회된 행 수: {len(rows)}")

            # 시간/날짜 포맷 변환
            for row in rows:
                if row.get('start_time') and not isinstance(row['start_time'], str):
                    try:
                        row['start_time'] = row['start_time'].strftime('%H:%M')
                    except Exception:
                        pass
                if row.get('end_time') and not isinstance(row['end_time'], str):
                    try:
                        row['end_time'] = row['end_time'].strftime('%H:%M')
                    except Exception:
                        pass
                # Normalize ISO datetime fields for client convenience
                try:
                    # prefer start_time as full datetime if provided, otherwise combine 'year' date + start_time
                    start_dt = None
                    if row.get('start_time') and isinstance(row['start_time'], str) and '-' in row['start_time']:
                        # already a datetime-like string
                        try:
                            # try parsing
                            start_dt = datetime.fromisoformat(row['start_time'])
                        except Exception:
                            try:
                                start_dt = datetime.strptime(row['start_time'], '%Y-%m-%d %H:%M:%S')
                            except Exception:
                                start_dt = None
                    elif row.get('year') and row.get('start_time'):
                        # combine date portion of 'year' with time portion in start_time
                        try:
                            d = row['year'] if isinstance(row['year'], datetime) else datetime.fromisoformat(str(row['year']))
                            t_str = row['start_time'] if isinstance(row['start_time'], str) else ''
                            # ensure time has seconds
                            if t_str and t_str.count(':')==1:
                                t_str = t_str + ':00'
                            if t_str:
                                start_dt = datetime.fromisoformat(d.strftime('%Y-%m-%d') + 'T' + t_str)
                        except Exception:
                            start_dt = None
                    # attach ISO string if we could parse
                    if start_dt:
                        row['start_datetime'] = start_dt.isoformat(sep=' ')
                    else:
                        row['start_datetime'] = None

                    # same for end_time
                    end_dt = None
                    if row.get('end_time') and isinstance(row['end_time'], str) and '-' in row['end_time']:
                        try:
                            end_dt = datetime.fromisoformat(row['end_time'])
                        except Exception:
                            try:
                                end_dt = datetime.strptime(row['end_time'], '%Y-%m-%d %H:%M:%S')
                            except Exception:
                                end_dt = None
                    elif row.get('year') and row.get('end_time'):
                        try:
                            d = row['year'] if isinstance(row['year'], datetime) else datetime.fromisoformat(str(row['year']))
                            t_str = row['end_time'] if isinstance(row['end_time'], str) else ''
                            if t_str and t_str.count(':')==1:
                                t_str = t_str + ':00'
                            if t_str:
                                end_dt = datetime.fromisoformat(d.strftime('%Y-%m-%d') + 'T' + t_str)
                        except Exception:
                            end_dt = None
                    if end_dt:
                        row['end_datetime'] = end_dt.isoformat(sep=' ')
                    else:
                        row['end_datetime'] = None
                except Exception:
                    row['start_datetime'] = None
                    row['end_datetime'] = None
            return rows
    finally:
        conn.close()

class UserLogin(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    training_key: str
    username: str
    password: str

class MoveContentRequest(BaseModel):
    new_lab_id: int

class ReorderContentRequest(BaseModel):
    new_view_number: int

class ContentViewLog(BaseModel):
    training_key: str
    member_id: str
    lab_id: int
    content_id: int

class TrainingKeyCheckRequest(BaseModel):
    training_key: str

class RegisterRequest(BaseModel):
    training_key: str
    name: str
    password: str

@app.get("/")
async def read_root():
    return FileResponse("templates/index.html")

@app.post("/api/login")
async def login(data: LoginRequest):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 관리자 로그인인지 확인 (트레이닝 키가 비어있거나 'admin'인 경우)
            is_admin_login = not data.training_key or data.training_key.strip() == '' or data.training_key.lower() == 'admin'
            
            if is_admin_login:
                # 관리자 로그인: 모든 training_member 테이블에서 사용자 검색
                sql = "SELECT member_password, role, training_key FROM training_member WHERE member_id = %s"
                cursor.execute(sql, (data.username,))
                result = cursor.fetchone()
                
                if not result:
                    raise HTTPException(status_code=400, detail="존재하지 않는 사용자입니다.")
                
                if result['member_password'] != data.password:
                    raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")
                
                role = result['role']
                training_key = result['training_key']
                
                # 관리자 권한 체크 (role >= 100)
                if role < 100:
                    raise HTTPException(status_code=400, detail="관리자 권한이 없습니다.")
                
            else:
                # 일반 사용자 로그인: 기존 로직
                # 먼저 트레이닝 키가 유효한지 확인
                cursor.execute("SELECT 1 FROM training WHERE training_key = %s", (data.training_key,))
                training_exists = cursor.fetchone()
                if not training_exists:
                    raise HTTPException(status_code=400, detail="트레이닝 키가 존재하지 않습니다. 다시 한번 확인해 주세요.")
                
                # 해당 트레이닝 키에 속한 사용자가 있는지 확인
                cursor.execute("SELECT member_id FROM training_member WHERE training_key = %s", (data.training_key,))
                members = cursor.fetchall()
                if not members:
                    raise HTTPException(status_code=400, detail="해당 트레이닝 키에 등록된 회원이 없습니다.")
                
                # 입력한 사용자 ID가 해당 트레이닝에 속하는지 확인
                member_ids = [member['member_id'] for member in members]
                if data.username not in member_ids:
                    raise HTTPException(status_code=400, detail=f"해당 트레이닝에 '{data.username}' 사용자가 존재하지 않습니다.")
                
                # 비밀번호 확인
                sql = "SELECT member_password, role FROM training_member WHERE training_key = %s AND member_id = %s"
                cursor.execute(sql, (data.training_key, data.username))
                result = cursor.fetchone()
                
                if result['member_password'] != data.password:
                    raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")
                
                role = result['role']
                training_key = data.training_key
            
        return {"message": "Login successful", "role": role, "training_key": training_key}
    finally:
        conn.close()

@app.post("/api/check-training-key")
async def check_training_key(data: TrainingKeyCheckRequest):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT training_key FROM training WHERE training_key = %s"
            cursor.execute(sql, (data.training_key,))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=400, detail="유효하지 않은 트레이닝 키입니다.")
            
            return {"message": "Valid training key"}
    finally:
        conn.close()

@app.post("/api/next-member-key")
async def next_member_key(data: TrainingKeyCheckRequest):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT MAX(member_key) as max_key FROM training_member WHERE training_key = %s"
            cursor.execute(sql, (data.training_key,))
            result = cursor.fetchone()
            next_key = 1 if not result or result['max_key'] is None else int(result['max_key']) + 1
            member_id = f"labuser{next_key}"
        return {"next_member_key": next_key, "member_id": member_id}
    finally:
        conn.close()

@app.post("/api/register")
async def register_user(data: RegisterRequest):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 트레이닝 키 유효성 검사
            cursor.execute("SELECT 1 FROM training WHERE training_key = %s", (data.training_key,))
            valid_key = cursor.fetchone()
            if not valid_key:
                raise HTTPException(status_code=400, detail="유효하지 않은 트레이닝 키입니다.")
            
            # 다음 member_key 구하기
            cursor.execute("SELECT MAX(member_key) as max_key FROM training_member WHERE training_key = %s", (data.training_key,))
            result = cursor.fetchone()
            next_key = 1 if not result or result['max_key'] is None else int(result['max_key']) + 1
            member_id = f"labuser{next_key}"
            
            # 중복 체크
            cursor.execute("SELECT 1 FROM training_member WHERE training_key = %s AND member_id = %s", (data.training_key, member_id))
            existing_member = cursor.fetchone()
            if existing_member:
                raise HTTPException(status_code=400, detail="이미 존재하는 회원입니다.")
            
            # 회원 등록
            try:
                cursor.execute(
                    "INSERT INTO training_member (member_key, training_key, member_id, member_name, member_password, role, create_date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        next_key,
                        data.training_key,
                        member_id,
                        data.name,
                        data.password,
                        10,  # 일반 사용자 역할
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    )
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"회원 생성 실패: {str(e)}")
            
        return {"message": "Registration successful", "member_id": member_id, "name": data.name}
    finally:
        conn.close()

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



@app.get("/portal/lab_content")
async def portal_lab_content_page():
    return FileResponse("templates/portal_lab_content.html")

@app.get("/api/admin/users")
async def get_users():
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT member_id, member_name, role, create_date FROM training_member ORDER BY create_date DESC")
            result = cursor.fetchall()
            users = [{"member_id": row['member_id'], "member_name": row['member_name'], "role": row['role'], "create_date": row['create_date'].strftime('%Y-%m-%d %H:%M') if row['create_date'] else ''} for row in result]
        return users
    finally:
        conn.close()

@app.get("/api/admin/users/course/{training_key}")
async def get_users_by_course(training_key: str):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 사용자 정보와 마지막으로 본 콘텐츠 정보를 함께 조회
            cursor.execute("""
                SELECT 
                    tm.member_id, 
                    tm.member_name, 
                    tm.role, 
                    tm.create_date,
                    tll.lab_id,
                    tll.content_id,
                    tlc.lab_content_subject,
                    tl.lab_name,
                    tll.create_date as last_view_date
                FROM training_member tm
                LEFT JOIN (
                    SELECT 
                        member_key, 
                        lab_id, 
                        content_id, 
                        create_date,
                        ROW_NUMBER() OVER (PARTITION BY member_key ORDER BY create_date DESC) as rn
                    FROM training_lab_log 
                    WHERE training_key = %s
                ) tll ON tm.member_key = tll.member_key AND tll.rn = 1
                LEFT JOIN training_lab_contents tlc ON tll.lab_id = tlc.lab_id AND tll.content_id = tlc.content_id AND tlc.training_key = %s
                LEFT JOIN training_lab tl ON tll.lab_id = tl.lab_id AND tl.training_key = %s
                WHERE tm.training_key = %s 
                ORDER BY tm.create_date DESC
            """, (training_key, training_key, training_key, training_key))
            result = cursor.fetchall()
            
            users = []
            for row in result:
                last_content_info = ""
                if row['lab_id'] and row['content_id']:
                    last_content_info = f"{row['lab_name']} - {row['lab_content_subject']}"
                    if row['last_view_date']:
                        last_content_info += f" ({row['last_view_date'].strftime('%Y-%m-%d %H:%M')})"
                
                users.append({
                    "member_id": row['member_id'], 
                    "member_name": row['member_name'], 
                    "role": row['role'], 
                    "create_date": row['create_date'].strftime('%Y-%m-%d %H:%M') if row['create_date'] else '',
                    "last_content": last_content_info
                })
        return users
    finally:
        conn.close()

@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: str):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM training_member WHERE member_id = %s", (user_id,))
        return {"message": "User deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")
    finally:
        conn.close()

@app.get("/api/admin/courses")
async def get_courses():
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT training_key, course_name, course_content, max_member, create_date, training_status FROM training ORDER BY create_date DESC")
            result = cursor.fetchall()
            courses = [
                {
                    "training_key": row['training_key'],
                    "course_name": row['course_name'],
                    "course_content": row['course_content'],
                    "max_member": row['max_member'],
                    "create_date": row['create_date'].strftime('%Y-%m-%d %H:%M') if row['create_date'] else '',
                    "training_status": row['training_status']
                }
                for row in result
            ]
        return courses
    finally:
        conn.close()

@app.get("/api/admin/courses/{training_key}")
async def get_course(training_key: str):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT training_key, course_name, course_content, max_member, create_date, training_status FROM training WHERE training_key = %s", (training_key,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="과정을 찾을 수 없습니다.")
            return {
                "training_key": row['training_key'],
                "course_name": row['course_name'],
                "course_content": row['course_content'],
                "max_member": row['max_member'],
                "create_date": row['create_date'].strftime('%Y-%m-%d %H:%M') if row['create_date'] else '',
                "training_status": row['training_status']
            }
    finally:
        conn.close()

@app.post("/api/admin/courses")
async def add_course(data: dict = Body(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            now = datetime.now()
            date_str = now.strftime('%Y%m%d')
            # 일련번호 01~99까지 시도
            for seq in range(1, 100):
                training_key = f"{date_str}{seq:02d}"
                cursor.execute("SELECT 1 FROM training WHERE training_key = %s", (training_key,))
                exists = cursor.fetchone()
                if not exists:
                    break
            else:
                raise HTTPException(status_code=500, detail="오늘은 더 이상 코스를 생성할 수 없습니다.")
            try:
                cursor.execute(
                    "INSERT INTO training (training_key, course_name, course_content, max_member, create_date, training_status) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        training_key,
                        data.get("course_name"),
                        data.get("course_content"),
                        data.get("max_member"),
                        now,
                        data.get("training_status")
                    )
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"코스 추가 실패: {str(e)}")
        return {"message": "코스가 추가되었습니다."}
    finally:
        conn.close()

@app.put("/api/admin/courses/{training_key}")
async def update_course(training_key: str, data: dict = Body(...)):
    print(f"update_course called: training_key={training_key}, data={data}")
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "UPDATE training SET course_name=%s, course_content=%s, max_member=%s, training_status=%s WHERE training_key=%s",
                    (
                        data.get("course_name"),
                        data.get("course_content"),
                        int(data.get("max_member")),
                        data.get("training_status"),
                        training_key
                    )
                )
            except Exception as e:
                print(f"코스 수정 실패: {e}")
                raise HTTPException(status_code=500, detail=f"코스 수정 실패: {str(e)}")
        return {"message": "코스가 수정되었습니다."}
    finally:
        conn.close()

@app.delete("/api/admin/courses/{training_key}")
async def delete_course(training_key: str):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM training WHERE training_key = %s", (training_key,))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"코스 삭제 실패: {str(e)}")
        return {"message": "코스가 삭제되었습니다."}
    finally:
        conn.close()

@app.get("/api/debug/labs")
async def debug_labs():
    """디버깅용: 모든 랩 데이터 조회"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM training_lab ORDER BY lab_id")
            result = cursor.fetchall()
            return {"all_labs": result}
    finally:
        conn.close()

@app.get("/api/admin/labs")
async def get_labs(training_key: str = Query(...)):
    print(f"[DEBUG] Getting labs for training_key: {training_key}")
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            sql = '''
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
                WHERE l.training_key = %s
                ORDER BY l.lab_id
            '''
            cursor.execute(sql, (training_key,))
            result = cursor.fetchall()
            print(f"[DEBUG] Raw lab data from database: {result}")
            
            labs = []
            for row in result:
                lab_dict = {
                    "lab_id": row['lab_id'],
                    "training_key": row['training_key'],
                    "lab_name": row['lab_name'],
                    "lab_content": row['lab_content'],
                    "lab_status": row['lab_status'],
                    "create_date": row['create_date'].strftime('%Y-%m-%d %H:%M') if row['create_date'] else '',
                    "content_count": int(row['content_count'])
                }
                labs.append(lab_dict)
            print(f"[DEBUG] Processed labs data: {labs}")
            return labs
    except Exception as e:
        print(f"Error in get_labs: {e}")
        raise HTTPException(status_code=500, detail=f"랩 목록을 불러오는데 실패했습니다: {str(e)}")
    finally:
        conn.close()

@app.get("/api/admin/labs/{lab_id}")
async def get_lab(lab_id: int):
    print(f"[DEBUG] Getting lab with ID: {lab_id}")
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 먼저 해당 training_key의 모든 랩을 조회해서 디버깅
            cursor.execute("SELECT lab_id, training_key, lab_name, lab_content, lab_status, create_date FROM training_lab ORDER BY lab_id")
            all_labs = cursor.fetchall()
            print(f"[DEBUG] All labs in database: {all_labs}")
            
            # 특정 lab_id 조회
            cursor.execute("SELECT lab_id, training_key, lab_name, lab_content, lab_status, create_date FROM training_lab WHERE lab_id = %s", (lab_id,))
            result = cursor.fetchone()
            if not result:
                print(f"[DEBUG] Lab not found with ID: {lab_id}")
                raise HTTPException(status_code=404, detail=f"랩 ID {lab_id}를 찾을 수 없습니다.")
            
            lab = {
                "lab_id": result['lab_id'],
                "training_key": result['training_key'],
                "lab_name": result['lab_name'],
                "lab_content": result['lab_content'],
                "lab_status": result['lab_status'],
                "create_date": result['create_date'].strftime('%Y-%m-%d %H:%M') if result['create_date'] else ''
            }
            print(f"[DEBUG] Returning lab data: {lab}")
            return lab
    except Exception as e:
        print(f"[ERROR] Error getting lab {lab_id}: {e}")
        raise HTTPException(status_code=500, detail=f"랩 정보를 불러오는데 실패했습니다: {str(e)}")
    finally:
        conn.close()

@app.post("/api/admin/labs")
async def add_lab(data: dict = Body(...)):
    print(f"[DEBUG] add_lab called: training_key={data.get('training_key')}, lab_name={data.get('lab_name')}")
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 해당 training_key에서 가장 큰 lab_id 조회
            cursor.execute("SELECT MAX(lab_id) as max_lab_id FROM training_lab WHERE training_key = %s", (data.get("training_key"),))
            result = cursor.fetchone()
            current_max_id = result['max_lab_id'] if result and result['max_lab_id'] is not None else 0
            next_lab_id = current_max_id + 1
            
            print(f"[DEBUG] Current max lab_id for training_key {data.get('training_key')}: {current_max_id}")
            print(f"[DEBUG] Next lab_id will be: {next_lab_id}")
            
            now = datetime.now()
            try:
                cursor.execute(
                    "INSERT INTO training_lab (lab_id, training_key, lab_name, lab_content, lab_status, create_date) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        next_lab_id,
                        data.get("training_key"),
                        data.get("lab_name"),
                        data.get("lab_content"),
                        data.get("lab_status", 20),  # 기본값을 활성화(20)로 설정
                        now
                    )
                )
                print(f"[DEBUG] Lab added successfully with lab_id: {next_lab_id}")
            except Exception as e:
                print(f"[ERROR] Lab insertion failed: {e}")
                raise HTTPException(status_code=500, detail=f"랩 추가 실패: {str(e)}")
        return {"message": "랩이 추가되었습니다.", "lab_id": next_lab_id}
    finally:
        conn.close()

@app.put("/api/admin/labs/{lab_id}")
async def update_lab(lab_id: int, data: dict = Body(...)):
    print(f"[DEBUG] update_lab called: lab_id={lab_id}, data={data}")
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 먼저 해당 랩이 존재하는지 확인
            cursor.execute("SELECT 1 FROM training_lab WHERE lab_id = %s", (lab_id,))
            lab_exists = cursor.fetchone()
            if not lab_exists:
                raise HTTPException(status_code=404, detail=f"랩 ID {lab_id}를 찾을 수 없습니다.")
            
            try:
                # 상태만 업데이트하는 경우
                if "lab_status" in data and len(data) == 2:  # lab_status와 training_key만 있는 경우
                    cursor.execute(
                        "UPDATE training_lab SET lab_status=%s WHERE lab_id=%s AND training_key=%s",
                        (
                            data.get("lab_status"),
                            lab_id,
                            data.get("training_key")
                        )
                    )
                else:
                    # 전체 업데이트 (랩명, 내용, 상태 모두)
                    cursor.execute(
                        "UPDATE training_lab SET lab_name=%s, lab_content=%s, lab_status=%s WHERE lab_id=%s AND training_key=%s",
                        (
                            data.get("lab_name"),
                            data.get("lab_content"),
                            data.get("lab_status"),
                            lab_id,
                            data.get("training_key")
                        )
                    )
                
                # 업데이트된 행 수 확인
                if cursor.rowcount == 0:
                    raise HTTPException(status_code=400, detail="랩을 수정할 수 없습니다. training_key가 일치하지 않을 수 있습니다.")
                
                print(f"[DEBUG] Lab update successful for lab_id={lab_id}, rows affected: {cursor.rowcount}")
            except Exception as e:
                print(f"[ERROR] 랩 수정 실패: {e}")
                raise HTTPException(status_code=500, detail=f"랩 수정 실패: {str(e)}")
        return {"message": "랩이 수정되었습니다."}
    finally:
        conn.close()

@app.delete("/api/admin/labs/{lab_id}")
async def delete_lab(lab_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM training_lab WHERE lab_id = %s", (lab_id,))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"랩 삭제 실패: {str(e)}")
        return {"message": "랩이 삭제되었습니다."}
    finally:
        conn.close()

@app.get("/api/portal-info")
async def portal_info(request: Request):
    member_id = request.query_params.get("member_id")
    training_key = request.query_params.get("training_key")
    if not member_id or not training_key:
        raise HTTPException(status_code=400, detail="member_id 및 training_key가 필요합니다.")
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 사용자 정보 확인 및 member_name 조회
            cursor.execute("SELECT member_name FROM training_member WHERE training_key = %s AND member_id = %s", (training_key, member_id))
            member_result = cursor.fetchone()
            if not member_result:
                raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다.")
            member_name = member_result['member_name']

            # 과정명 및 상태 조회
            cursor.execute("SELECT course_name, training_status FROM training WHERE training_key = %s", (training_key,))
            course_row = cursor.fetchone()
            course_name = course_row['course_name'] if course_row else None
            course_status = course_row['training_status'] if course_row else None

            # 랩 목록 조회
            cursor.execute("SELECT lab_id, lab_name, lab_content, lab_status, create_date FROM training_lab WHERE training_key = %s ORDER BY lab_id ASC", (training_key,))
            labs_result = cursor.fetchall()
            lab_list = []
            for r in labs_result:
                lab_list.append({
                    "lab_id": r['lab_id'],
                    "lab_name": r['lab_name'],
                    "lab_content": r['lab_content'],
                    "lab_status": r['lab_status'],
                    "create_date": r['create_date'].strftime('%Y-%m-%d %H:%M') if r['create_date'] else ''
                })
        return {
            "member_id": member_id,
            "training_key": training_key,
            "member_name": member_name,
            "course_name": course_name,
            "course_status": course_status,
            "labs": lab_list
        }
    finally:
        conn.close()

@app.get("/api/portal-labs")
async def portal_labs(request: Request):
    training_key = request.query_params.get("training_key")
    if not training_key:
        raise HTTPException(status_code=400, detail="training_key가 필요합니다.")
    
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 먼저 해당 트레이닝이 존재하는지 확인
            cursor.execute("""
                SELECT training_status, course_name 
                FROM training 
                WHERE training_key = %s
            """, (training_key,))
            training_result = cursor.fetchone()
            
            if not training_result:
                return {"labs": [], "message": "트레이닝을 찾을 수 없습니다."}
            
            # 랩 목록 조회 (모든 랩)
            try:
                cursor.execute("""
                    SELECT lab_id, lab_name, lab_content, lab_status, create_date 
                    FROM training_lab 
                    WHERE training_key = %s
                    ORDER BY lab_id ASC
                """, (training_key,))
                labs_result = cursor.fetchall()
                
                print(f"[DEBUG] portal_labs - 조회된 랩 개수: {len(labs_result)}")
                
                lab_list = []
                for r in labs_result:
                    print(f"[DEBUG] 랩 데이터: lab_id={r['lab_id']}, lab_name={r['lab_name']}, lab_status={r['lab_status']} (타입: {type(r['lab_status'])})")
                    lab_list.append({
                        "lab_id": r['lab_id'],
                        "lab_name": r['lab_name'],
                        "lab_content": r['lab_content'],
                        "lab_status": r['lab_status'],
                        "create_date": r['create_date'].strftime('%Y-%m-%d %H:%M') if r['create_date'] else ''
                    })
                
                print(f"[DEBUG] 최종 반환할 lab_list: {lab_list}")
            except Exception as e:
                print(f"[ERROR] 랩 목록 조회 실패: {e}")
                lab_list = []
            
        return {
            "labs": lab_list, 
            "training_name": training_result['course_name'],
            "training_status": training_result['training_status']
        }
    except Exception as e:
        print(f"[ERROR] portal_labs 오류: {e}")
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")
    finally:
        conn.close()

@app.get("/api/admin/lab_user_counts")
async def get_lab_user_counts(training_key: str = Query(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            sql = '''
                SELECT 
                    tl.lab_id,
                    tl.lab_name,
                    COUNT(DISTINCT tll.member_key) AS user_count
                FROM training_lab tl
                LEFT JOIN training_lab_log tll ON tl.lab_id = tll.lab_id AND tl.training_key = tll.training_key
                WHERE tl.training_key = %s
                GROUP BY tl.lab_id, tl.lab_name
                ORDER BY tl.lab_id
            '''
            cursor.execute(sql, (training_key,))
            result = cursor.fetchall()
            lab_counts = []
            for row in result:
                lab_counts.append({
                    "lab_id": row['lab_id'],
                    "lab_name": row['lab_name'],
                    "user_count": row['user_count']
                })
            return lab_counts
    except Exception as e:
        print(f"[ERROR] Error fetching lab user counts: {e}")
        raise HTTPException(status_code=500, detail=f"랩별 사용자 수를 불러오는데 실패했습니다: {str(e)}")
    finally:
        conn.close()

@app.get("/api/admin/user_content_progress")
async def get_user_content_progress(
    training_key: str = Query(...),
    lab_id: int = Query(...)
):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1. 해당 랩의 모든 콘텐츠 (view_number 순서대로)
            cursor.execute("SELECT content_id, lab_content_subject FROM training_lab_contents WHERE training_key = %s AND lab_id = %s ORDER BY view_number ASC", (training_key, lab_id))
            all_contents = cursor.fetchall()
            contents_list = []
            for c in all_contents:
                contents_list.append({"content_id": c['content_id'], "lab_content_subject": c['lab_content_subject']})

            # 2. 해당 랩에 접근한 모든 사용자
            cursor.execute("""
                SELECT DISTINCT tm.member_key, tm.member_id, tm.member_name
                FROM training_member tm
                JOIN training_lab_log tll ON tm.member_key = tll.member_key AND tm.training_key = tll.training_key
                WHERE tm.training_key = %s AND tll.lab_id = %s
                ORDER BY tm.member_key ASC
            """, (training_key, lab_id))
            all_users = cursor.fetchall()
            users_list = []
            for u in all_users:
                cursor.execute("SELECT DISTINCT content_id FROM training_lab_log WHERE training_key = %s AND member_key = %s AND lab_id = %s", (training_key, u['member_key'], lab_id))
                viewed_contents = cursor.fetchall()
                users_list.append({
                    "member_key": u['member_key'],
                    "member_id": u['member_id'],
                    "member_name": u['member_name'],
                    "viewed_contents": [vc['content_id'] for vc in viewed_contents]
                })
            return {"users": users_list, "contents": contents_list}
    except Exception as e:
        print(f"[ERROR] Error fetching user content progress: {e}")
        raise HTTPException(status_code=500, detail=f"사용자 진도 데이터를 불러오는데 실패했습니다: {str(e)}")
    finally:
        conn.close()

@app.post("/api/portal/log_content_view")
async def log_content_view(log: ContentViewLog):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # member_id로 member_key 조회
            cursor.execute("SELECT member_key FROM training_member WHERE training_key = %s AND member_id = %s", (log.training_key, log.member_id))
            member_result = cursor.fetchone()
            if not member_result:
                raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
            member_key = member_result['member_key']

            # 로그 기록이 이미 존재하는지 확인
            cursor.execute("SELECT 1 FROM training_lab_log WHERE training_key = %s AND member_key = %s AND lab_id = %s AND content_id = %s", (log.training_key, member_key, log.lab_id, log.content_id))
            existing_log = cursor.fetchone()
            if existing_log:
                print(f"[DEBUG] 콘텐츠 조회 기록 이미 존재: training_key={log.training_key}, member_key={member_key}, lab_id={log.lab_id}, content_id={log.content_id}")
                return {"message": "Content view already logged"}

            # 로그 삽입 전 디버그 출력
            print(f"[DEBUG] Inserting log: training_key={log.training_key}, member_key={member_key}, lab_id={log.lab_id}, content_id={log.content_id}, create_date={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # 로그 기록
            cursor.execute(
                "INSERT INTO training_lab_log (training_key, member_key, lab_id, content_id, create_date) VALUES (%s, %s, %s, %s, %s)",
                (
                    log.training_key,
                    member_key,
                    log.lab_id,
                    log.content_id,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                )
            )
            print("[DEBUG] Content view log inserted successfully.")
            return {"message": "Content view logged successfully"}
    except Exception as e:
        print(f"[ERROR] Error during content view logging: {e}")
        raise HTTPException(status_code=500, detail=f"콘텐츠 조회 기록 실패: {str(e)}")
    finally:
        conn.close()

@app.get("/api/admin/lab_contents")
async def get_lab_contents(training_key: str = Query(...), lab_id: int = Query(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT training_key, lab_id, content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date FROM training_lab_contents WHERE training_key = %s AND lab_id = %s ORDER BY content_id ASC", (training_key, lab_id))
            result = cursor.fetchall()
            contents = [
                {
                    "training_key": row['training_key'],
                    "lab_id": row['lab_id'],
                    "content_id": row['content_id'],
                    "view_number": row['view_number'],
                    "lab_content_subject": row['lab_content_subject'],
                    "lab_content": row['lab_content'],
                    "lab_content_type": row['lab_content_type'],
                    "lab_content_status": row['lab_content_status'],
                    "lab_content_create_date": row['lab_content_create_date'].strftime('%Y-%m-%d %H:%M') if row['lab_content_create_date'] else ''
                }
                for row in result
            ]
        return contents
    finally:
        conn.close()

@app.get("/api/admin/lab_contents/{content_id}")
async def get_lab_content(content_id: int, training_key: str = Query(...), lab_id: int = Query(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date FROM training_lab_contents WHERE training_key = %s AND lab_id = %s AND content_id = %s", (training_key, lab_id, content_id))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다.")
            return {
                "content_id": row['content_id'],
                "view_number": row['view_number'],
                "lab_content_subject": row['lab_content_subject'],
                "lab_content": row['lab_content'],
                "lab_content_type": row['lab_content_type'],
                "lab_content_status": row['lab_content_status'],
                "lab_content_create_date": row['lab_content_create_date'].strftime('%Y-%m-%d %H:%M') if row['lab_content_create_date'] else ''
            }
    finally:
        conn.close()

@app.post("/api/admin/lab_contents")
async def add_lab_content(data: dict = Body(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # content_id는 lab별로 1부터 시작하는 일련번호
            cursor.execute("SELECT MAX(content_id) as max_content_id FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (data.get("training_key"), data.get("lab_id")))
            result_content_id = cursor.fetchone()
            next_content_id = 1 if not result_content_id or result_content_id['max_content_id'] is None else int(result_content_id['max_content_id']) + 1

            # view_number는 해당 lab 내에서 MAX(view_number) + 1로 설정
            cursor.execute("SELECT MAX(view_number) as max_view_number FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (data.get("training_key"), data.get("lab_id")))
            result_view_number = cursor.fetchone()
            next_view_number = 1 if not result_view_number or result_view_number['max_view_number'] is None else int(result_view_number['max_view_number']) + 1

            now = datetime.now()
            try:
                cursor.execute(
                    "INSERT INTO training_lab_contents (training_key, lab_id, content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        data.get("training_key"),
                        data.get("lab_id"),
                        next_content_id,
                        next_view_number,
                        data.get("lab_content_subject"),
                        data.get("lab_content"),
                        data.get("lab_content_type"),
                        data.get("lab_content_status"),
                        now
                    )
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"콘텐츠 추가 실패: {str(e)}")
        return {"message": "콘텐츠가 추가되었습니다."}
    finally:
        conn.close()

@app.put("/api/admin/lab_contents/{content_id}")
async def update_lab_content(content_id: int, data: dict = Body(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "UPDATE training_lab_contents SET lab_content_subject=%s, lab_content=%s, lab_content_status=%s, lab_content_type=%s WHERE training_key=%s AND lab_id=%s AND content_id=%s",
                    (
                        data.get("lab_content_subject"),
                        data.get("lab_content"),
                        data.get("lab_content_status"),
                        data.get("lab_content_type"),
                        data.get("training_key"),
                        data.get("lab_id"),
                        content_id
                    )
                )
            except Exception as e:
                print(f"콘텐츠 수정 실패: {e}")
                raise HTTPException(status_code=500, detail=f"콘텐츠 수정 실패: {str(e)}")
        return {"message": "콘텐츠가 수정되었습니다."}
    finally:
        conn.close()

@app.delete("/api/admin/lab_contents/{content_id}")
async def delete_lab_content(content_id: int, training_key: str = Query(...), lab_id: int = Query(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM training_lab_contents WHERE training_key = %s AND lab_id = %s AND content_id = %s", (training_key, lab_id, content_id))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"콘텐츠 삭제 실패: {str(e)}")
        return {"message": "콘텐츠가 삭제되었습니다."}
    finally:
        conn.close()

@app.put("/api/admin/lab_contents/{content_id}/status")
async def update_lab_content_status(
    content_id: int,
    training_key: str = Query(...),
    lab_id: int = Query(...),
    new_status: int = Body(..., embed=True)
):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "UPDATE training_lab_contents SET lab_content_status=%s WHERE training_key=%s AND lab_id=%s AND content_id=%s",
                    (new_status, training_key, lab_id, content_id)
                )
            except Exception as e:
                print(f"콘텐츠 상태 업데이트 실패: {e}")
                raise HTTPException(status_code=500, detail=f"콘텐츠 상태 업데이트 실패: {str(e)}")
        return {"message": "콘텐츠 상태가 성공적으로 업데이트되었습니다."}
    finally:
        conn.close()

@app.put("/api/admin/lab_contents/{content_id}/move")
async def move_lab_content(content_id: int, request: MoveContentRequest, training_key: str = Query(...)):
    print(f"move_lab_content called: content_id={content_id}, training_key={training_key}, new_lab_id={request.new_lab_id}")
    new_lab_id = request.new_lab_id
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1. 현재 콘텐츠 정보 조회
            cursor.execute("SELECT training_key, lab_id FROM training_lab_contents WHERE content_id = %s AND training_key = %s", (content_id, training_key))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다.")
            # 2. 새로운 랩이 같은 과정에 속하는지 확인
            cursor.execute("SELECT COUNT(*) as cnt FROM training_lab WHERE training_key = %s AND lab_id = %s", (training_key, new_lab_id))
            result2 = cursor.fetchone()
            if not result2 or result2['cnt'] == 0:
                raise HTTPException(status_code=400, detail="해당 랩이 과정에 존재하지 않습니다.")
            # 3. 콘텐츠 이동
            cursor.execute("UPDATE training_lab_contents SET lab_id = %s WHERE content_id = %s AND training_key = %s", (new_lab_id, content_id, training_key))
            return {"message": "콘텐츠가 성공적으로 이동되었습니다."}
    except Exception as e:
        print(f"콘텐츠 이동 중 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"콘텐츠 이동 중 오류가 발생했습니다: {str(e)}")
    finally:
        conn.close()

@app.put("/api/admin/lab_contents/{content_id}/reorder")
async def update_lab_content_order(
    content_id: int,
    training_key: str = Query(...),
    lab_id: int = Query(...),
    request_body: ReorderContentRequest = Body(...)
):
    new_view_number = request_body.new_view_number
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1. Get current view_number of the target content
            cursor.execute("SELECT view_number FROM training_lab_contents WHERE training_key = %s AND lab_id = %s AND content_id = %s", (training_key, lab_id, content_id))
            current_content_result = cursor.fetchone()
            if not current_content_result:
                raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다.")
            old_view_number = current_content_result['view_number']
            # 2. Get the total number of contents in the current lab
            cursor.execute("SELECT COUNT(*) as cnt FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (training_key, lab_id))
            total_count_result = cursor.fetchone()
            total_content_count = total_count_result['cnt'] if total_count_result and total_count_result['cnt'] is not None else 0
            effective_max_view_number_for_validation = max(1, total_content_count)
            print(f"[DEBUG] total_content_count: {total_content_count}, content_id: {content_id}, old_view_number: {old_view_number}, effective_max_view_number_for_validation: {effective_max_view_number_for_validation}, new_view_number: {new_view_number}")
            if new_view_number < 1 or new_view_number > effective_max_view_number_for_validation:
                raise HTTPException(status_code=400, detail=f"유효하지 않은 순서 번호입니다. 1에서 {effective_max_view_number_for_validation} 사이의 값을 입력해주세요.")
            if old_view_number == new_view_number:
                return {"message": "콘텐츠 순서가 변경되지 않았습니다."}
            # Reordering logic
            if old_view_number == 0:
                cursor.execute(
                    "UPDATE training_lab_contents SET view_number = view_number + 1 WHERE training_key = %s AND lab_id = %s AND view_number >= %s",
                    (training_key, lab_id, new_view_number)
                )
            elif new_view_number < old_view_number:
                cursor.execute(
                    "UPDATE training_lab_contents SET view_number = view_number + 1 WHERE training_key = %s AND lab_id = %s AND view_number >= %s AND view_number < %s",
                    (training_key, lab_id, new_view_number, old_view_number)
                )
            else:
                cursor.execute(
                    "UPDATE training_lab_contents SET view_number = view_number - 1 WHERE training_key = %s AND lab_id = %s AND view_number <= %s AND view_number > %s",
                    (training_key, lab_id, new_view_number, old_view_number)
                )
            cursor.execute(
                "UPDATE training_lab_contents SET view_number = %s WHERE training_key = %s AND lab_id = %s AND content_id = %s",
                (new_view_number, training_key, lab_id, content_id)
            )
            return {"message": "콘텐츠 순서가 성공적으로 업데이트되었습니다."}
    except Exception as e:
        print(f"콘텐츠 순서 변경 중 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"콘텐츠 순서 변경 중 오류가 발생했습니다: {str(e)}")
    finally:
        conn.close()

@app.get("/api/proxy-markdown")
async def proxy_markdown(url: str):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return HTMLResponse(content=resp.text, status_code=200)
    except Exception as e:
        return HTMLResponse(content=f"URL에서 마크다운을 불러올 수 없습니다.\n{e}", status_code=400)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)