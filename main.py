
from fastapi import FastAPI, HTTPException, Body, Query, Request, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import pymysql
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import os
import hashlib
import random
import asyncio
import json
import re
from collections import deque

try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
except Exception:
    BlobServiceClient = None
    ContentSettings = None

load_dotenv()

app = FastAPI()


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools_well_known():
    return {}

# 앱 시작 시 이벤트 로그 테이블 생성
@app.on_event("startup")
async def startup_event():
    try:
        ensure_event_logs_table()
        print("✅ 이벤트 로그 테이블 확인/생성 완료")
        ensure_supervisors_table()
        print("✅ 감독자 테이블 확인/생성 완료")
        ensure_test_categories_table()
        print("✅ 테스트 종목 테이블 확인/생성 완료")
        ensure_question_categories_table()
        print("✅ 문제 카테고리 테이블 확인/생성 완료")
        ensure_test_questions_table()
        print("✅ 테스트 문제 테이블 확인/생성 완료")
        ensure_generated_tests_table()
        print("✅ 랜덤 테스트 테이블 확인/생성 완료")
    except Exception as e:
        print(f"⚠️ 테이블 생성 실패: {str(e)}")

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
KST = ZoneInfo('Asia/Seoul')


def now_kst():
    return datetime.now(KST)


def now_kst_naive():
    return now_kst().replace(tzinfo=None)


# 실시간 모니터링을 위한 이벤트 큐
monitoring_events = deque(maxlen=100)  # 최근 100개 이벤트 저장


def ensure_event_logs_table():
    """이벤트 로그 테이블 생성 (없을 경우)"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    training_key VARCHAR(100),
                    event_type VARCHAR(50) NOT NULL,
                    event_category VARCHAR(50) NOT NULL,
                    user_id VARCHAR(100),
                    user_name VARCHAR(100),
                    target_type VARCHAR(50),
                    target_id VARCHAR(100),
                    target_name VARCHAR(255),
                    description TEXT,
                    details JSON,
                    ip_address VARCHAR(50),
                    user_agent TEXT,
                    create_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_training_key (training_key),
                    INDEX idx_event_type (event_type),
                    INDEX idx_create_date (create_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
    finally:
        conn.close()


def ensure_supervisors_table():
    """감독자 테이블 생성 (없을 경우)"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS training_supervisors (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    training_key VARCHAR(100) NOT NULL COLLATE utf8mb4_0900_ai_ci,
                    supervisor_name VARCHAR(100) NOT NULL COLLATE utf8mb4_0900_ai_ci,
                    is_active TINYINT DEFAULT 1,
                    create_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    update_date DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_supervisor (training_key, supervisor_name),
                    INDEX idx_training_key (training_key),
                    INDEX idx_supervisor_name (supervisor_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
            """)
            conn.commit()
    finally:
        conn.close()


def ensure_test_categories_table():
    """테스트 종목 테이블 생성 (없을 경우)"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_categories (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    category_name VARCHAR(100) NOT NULL,
                    description VARCHAR(500),
                    is_active TINYINT DEFAULT 1,
                    create_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    update_date DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_category_name (category_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
    finally:
        conn.close()


def ensure_question_categories_table():
    """문제 카테고리 테이블 생성 (없을 경우)"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS question_categories (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    category_name VARCHAR(100) NOT NULL,
                    description VARCHAR(500),
                    is_active TINYINT DEFAULT 1,
                    create_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    update_date DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_question_category_name (category_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
    finally:
        conn.close()


def ensure_test_questions_table():
    """테스트 문제 테이블 생성 (없을 경우)"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_questions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    test_category_id INT NOT NULL,
                    question_category_id INT NULL,
                    course_code VARCHAR(100) NULL,
                    question_number INT NULL,
                    question_category_name VARCHAR(100) NULL,
                    question_title VARCHAR(255) NOT NULL,
                    question_text TEXT,
                    image_urls_json LONGTEXT,
                    options_json LONGTEXT,
                    answer VARCHAR(50),
                    is_active TINYINT DEFAULT 1,
                    create_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    update_date DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_test_category_id (test_category_id),
                    INDEX idx_question_category_id (question_category_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            alter_statements = [
                "ALTER TABLE test_questions ADD COLUMN course_code VARCHAR(100) NULL AFTER question_category_id",
                "ALTER TABLE test_questions ADD COLUMN question_number INT NULL AFTER question_category_id",
                "ALTER TABLE test_questions ADD COLUMN question_type VARCHAR(50) NULL AFTER question_number",
                "ALTER TABLE test_questions ADD COLUMN question_category_name VARCHAR(100) NULL AFTER question_type",
                "ALTER TABLE test_questions ADD COLUMN image_urls_json LONGTEXT NULL AFTER question_text",
                "ALTER TABLE test_questions ADD COLUMN options_json LONGTEXT NULL AFTER question_text",
                "ALTER TABLE test_questions ADD COLUMN answer VARCHAR(50) NULL AFTER options_json"
            ]

            for statement in alter_statements:
                try:
                    cursor.execute(statement)
                except Exception as e:
                    if "Duplicate column name" not in str(e):
                        raise

            conn.commit()
    finally:
        conn.close()


def ensure_generated_tests_table():
    """랜덤 생성 테스트 테이블 생성 (없을 경우)"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS generated_tests (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    test_category_id INT NOT NULL,
                    generated_name VARCHAR(255) NOT NULL,
                    question_count INT NOT NULL DEFAULT 0,
                    selected_category_ids_json LONGTEXT,
                    selected_category_names_json LONGTEXT,
                    questions_json LONGTEXT,
                    is_random_order TINYINT DEFAULT 0,
                    is_full_selection TINYINT DEFAULT 0,
                    is_active TINYINT DEFAULT 1,
                    create_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    update_date DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_generated_tests_category_id (test_category_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            alter_statements = [
                "ALTER TABLE generated_tests ADD COLUMN question_count INT NOT NULL DEFAULT 0 AFTER generated_name",
                "ALTER TABLE generated_tests ADD COLUMN selected_category_ids_json LONGTEXT NULL AFTER question_count",
                "ALTER TABLE generated_tests ADD COLUMN selected_category_names_json LONGTEXT NULL AFTER selected_category_ids_json",
                "ALTER TABLE generated_tests ADD COLUMN questions_json LONGTEXT NULL AFTER selected_category_names_json",
                "ALTER TABLE generated_tests ADD COLUMN is_random_order TINYINT DEFAULT 0 AFTER questions_json",
                "ALTER TABLE generated_tests ADD COLUMN is_full_selection TINYINT DEFAULT 0 AFTER is_random_order",
                "ALTER TABLE generated_tests ADD COLUMN is_active TINYINT DEFAULT 1 AFTER questions_json"
            ]

            for statement in alter_statements:
                try:
                    cursor.execute(statement)
                except Exception as e:
                    if "Duplicate column name" not in str(e):
                        raise

            conn.commit()
    finally:
        conn.close()


def log_monitoring_event(training_key: str, event_type: str, details: dict, 
                         event_category: str = "system", user_id: str = None, 
                         user_name: str = None, target_type: str = None, 
                         target_id: str = None, target_name: str = None,
                         description: str = None):
    """모니터링 이벤트 기록 (메모리 큐 + 데이터베이스)"""
    event = {
        "timestamp": now_kst().isoformat(),
        "training_key": training_key,
        "type": event_type,
        "category": event_category,
        "user_id": user_id,
        "user_name": user_name,
        "target_type": target_type,
        "target_id": target_id,
        "target_name": target_name,
        "description": description,
        "details": details
    }
    monitoring_events.append(event)
    
    # 콘솔에 컬러로 출력
    event_icons = {
        "user_login": "🔐",
        "user_register": "👤",
        "lab_add": "➕",
        "lab_edit": "✏️",
        "lab_delete": "🗑️",
        "content_add": "📝",
        "content_edit": "✏️",
        "content_delete": "🗑️",
        "content_view": "👁️",
        "content_click": "🖱️"
    }
    icon = event_icons.get(event_type, "📋")
    
    print(f"\n{'='*60}")
    print(f"{icon} [모니터링 이벤트] {event_type}")
    print(f"   과정키: {training_key}")
    print(f"   사용자: {user_name} ({user_id})" if user_name else "")
    print(f"   대상: {target_type} - {target_name}" if target_type else "")
    print(f"   시간: {now_kst_str()}")
    print(f"   상세: {details}")
    print(f"   현재 큐 크기: {len(monitoring_events)}/100")
    print(f"{'='*60}\n")
    
    # 데이터베이스에 저장
    try:
        conn = get_mysql_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO event_logs 
                    (training_key, event_type, event_category, user_id, user_name, 
                     target_type, target_id, target_name, description, details, create_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    training_key, event_type, event_category, user_id, user_name,
                    target_type, target_id, target_name, description,
                    json.dumps(details, ensure_ascii=False),
                    now_kst_str('%Y-%m-%d %H:%M:%S')
                ))
                conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️ 이벤트 로그 DB 저장 실패: {str(e)}")


def now_kst_str(fmt: str = '%Y-%m-%d %H:%M:%S'):
    return now_kst().strftime(fmt)


def format_kst(dt_value, fmt: str = '%Y-%m-%d %H:%M'):
    if not dt_value:
        return ''
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=KST)
    else:
        dt_value = dt_value.astimezone(KST)
    return dt_value.strftime(fmt)


def normalize_lab_content_type(raw_type):
    if raw_type is None:
        return 4

    if isinstance(raw_type, int):
        return raw_type

    value = str(raw_type).strip().lower()
    mapping = {
        '0': 0,
        'web_markdown': 0,
        'url_markdown': 0,
        '1': 1,
        'web': 1,
        '2': 2,
        'markdown': 2,
        '3': 3,
        'code': 3,
        '4': 4,
        'text': 4,
    }
    if value in mapping:
        return mapping[value]

    try:
        return int(value)
    except Exception:
        return 4


def sanitize_filename_part(value: str, default_value: str = "none") -> str:
    text = (value or "").strip()
    if not text:
        return default_value
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w\-]", "_", text, flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or default_value


def get_blob_service_client():
    if BlobServiceClient is None:
        raise HTTPException(status_code=500, detail="azure-storage-blob 패키지가 설치되지 않았습니다.")

    conn_str = (
        os.getenv("STORAGE_CONNECTION_STRING")
        or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        or os.getenv("BLOB_STORAGE_CONNECTION_STRING")
    )
    if conn_str:
        # Some .env files accidentally include an extra '=' after the key assignment.
        conn_str = conn_str.lstrip("=")
        return BlobServiceClient.from_connection_string(conn_str)

    account_name = os.getenv("STORAGE_ACCOUNT_NAME")
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    if not account_url and account_name:
        account_url = f"https://{account_name}.blob.core.windows.net"

    account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or os.getenv("STORAGE_ACCOUNT_KEY")
    sas_token = os.getenv("AZURE_STORAGE_SAS_TOKEN")

    credential = account_key or sas_token
    if account_url and credential:
        return BlobServiceClient(account_url=account_url, credential=credential)

    raise HTTPException(
        status_code=500,
        detail="Blob Storage 연결 정보가 없습니다. STORAGE_CONNECTION_STRING 또는 AZURE_STORAGE_CONNECTION_STRING을 설정해주세요."
    )


def get_blob_container_name(default_name: str = "question") -> str:
    container_name = os.getenv("STORAGE_CONTAINER_NAME", default_name)
    container_name = (container_name or default_name).strip().lower()
    return container_name or default_name

def get_mysql_conn():
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=30,
            ssl={'ssl': True}
        )
        return conn
    except Exception as e:
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
    try:
        conn = get_mysql_conn()
    except Exception as e:
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

class MoveContentRequest(BaseModel):
    new_lab_id: int

class BulkMoveContentRequest(BaseModel):
    content_ids: List[int]
    new_lab_id: int
    target_training_key: Optional[str] = None

class BulkCopyContentRequest(BaseModel):
    content_ids: List[int]
    target_training_key: str
    target_lab_id: int

class ReorderContentRequest(BaseModel):
    new_view_number: int

class ContentViewLog(BaseModel):
    training_key: str
    member_id: str
    lab_id: int
    content_id: int

class LabViewLog(BaseModel):
    training_key: str
    member_id: str
    lab_id: int

class TrainingKeyCheckRequest(BaseModel):
    training_key: str

class RegisterRequest(BaseModel):
    training_key: str
    username: str
    name: str

@app.get("/")
async def read_root():
    return FileResponse("templates/index.html")

@app.post("/api/login")
async def login(data: LoginRequest):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 트레이닝 키가 유효한지 확인
            cursor.execute("SELECT 1 FROM training WHERE training_key = %s", (data.training_key,))
            training_exists = cursor.fetchone()
            if not training_exists:
                raise HTTPException(status_code=400, detail="트레이닝 키가 존재하지 않습니다. 다시 한번 확인해 주세요.")
            
            # 해당 트레이닝 키에 속한 사용자를 이름(member_name)으로 조회
            sql = "SELECT member_id, role FROM training_member WHERE training_key = %s AND member_name = %s"
            cursor.execute(sql, (data.training_key, data.username))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=400, detail="해당 트레이닝에 등록된 사용자가 없습니다. 이름을 다시 확인해 주세요.")
            
            role = result['role']
            member_id = result['member_id']
            training_key = data.training_key
            
            # 로그인 이벤트 기록
            log_monitoring_event(
                training_key=training_key,
                event_type="user_login",
                event_category="auth",
                user_id=member_id,
                user_name=data.username,
                description=f"{data.username} 사용자가 로그인했습니다",
                details={"role": role}
            )
            
        return {
            "message": "Login successful", 
            "role": role, 
            "training_key": training_key,
            "member_id": member_id,
            "member_name": data.username
        }
    finally:
        conn.close()

@app.post("/api/logout")
async def logout(data: dict = Body(...)):
    """로그아웃 이벤트 로그 기록"""
    training_key = data.get("training_key")
    member_id = data.get("member_id")
    member_name = data.get("member_name")
    
    if training_key and member_id:
        log_monitoring_event(
            training_key=training_key,
            event_type="user_logout",
            event_category="auth",
            user_id=member_id,
            user_name=member_name,
            description=f"{member_name} 사용자가 로그아웃했습니다",
            details={}
        )
    
    return {"message": "Logout successful"}

@app.post("/api/portal/log_lab_view")
async def log_lab_view(data: dict = Body(...)):
    """랩 선택(조회) 이벤트 로그 기록"""
    training_key = data.get("training_key")
    member_id = data.get("member_id")
    lab_id = data.get("lab_id")
    
    if not all([training_key, member_id, lab_id]):
        raise HTTPException(status_code=400, detail="필수 파라미터가 누락되었습니다")
    
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 사용자 정보 조회
            cursor.execute("SELECT member_name FROM training_member WHERE training_key = %s AND member_id = %s", 
                         (training_key, member_id))
            member_info = cursor.fetchone()
            
            # 랩 정보 조회
            cursor.execute("SELECT lab_name FROM training_lab WHERE training_key = %s AND lab_id = %s", 
                         (training_key, lab_id))
            lab_info = cursor.fetchone()
            
            if member_info and lab_info:
                log_monitoring_event(
                    training_key=training_key,
                    event_type="lab_view",
                    event_category="lab",
                    user_id=member_id,
                    user_name=member_info['member_name'],
                    target_type="lab",
                    target_id=str(lab_id),
                    target_name=lab_info['lab_name'],
                    description=f"{member_info['member_name']} 사용자가 '{lab_info['lab_name']}' 랩을 선택했습니다",
                    details={"lab_id": lab_id}
                )
        
        return {"message": "Lab view logged"}
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
            # Users will provide their own username instead of labuser1, 2, etc.
            member_id = None
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
            
            # 이름 중복 체크 및 숫자 붙이기
            member_name = data.name
            suffix = 0
            duplicated = False
            
            while True:
                cursor.execute(
                    "SELECT 1 FROM training_member WHERE training_key = %s AND member_name = %s",
                    (data.training_key, member_name)
                )
                check = cursor.fetchone()
                if check:
                    suffix += 1
                    member_name = f"{data.name}{suffix}"
                    duplicated = True
                else:
                    break
            
            # 아이디 자동 생성: labuser1, labuser2, labuser3...
            member_id = f"labuser{next_key}"
            
            # 회원 등록
            try:
                cursor.execute(
                    "INSERT INTO training_member (member_key, training_key, member_id, member_name, member_password, role, create_date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        next_key,
                        data.training_key,
                        member_id,
                        member_name,
                        "",  # 비밀번호 없음
                        10,  # 일반 사용자 역할
                        now_kst_str('%Y-%m-%d %H:%M:%S')
                    )
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"회원 생성 실패: {str(e)}")
            
            conn.commit()
            
            # 모니터링 이벤트 기록
            log_monitoring_event(
                training_key=data.training_key,
                event_type="user_register",
                event_category="user",
                user_id=member_id,
                user_name=member_name,
                target_type="member",
                target_id=member_id,
                target_name=member_name,
                description=f"새로운 사용자 '{member_name}'이(가) 등록되었습니다",
                details={
                    "member_id": member_id,
                    "member_name": member_name,
                    "duplicated": duplicated,
                    "order": next_key
                }
            )
            
            response = {"message": "Registration successful", "member_id": member_id, "name": data.name, "registered_name": member_name, "order": next_key}
            if duplicated:
                response["warning"] = f"입력한 이름 '{data.name}'이(가) 중복되어 '{member_name}'으로 등록되었습니다."
                # 일련번호 추출 (예: "홍길동1" -> 1)
                response["suffix"] = member_name[len(data.name):]
            
            return response
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

@app.post("/api/admin/login")
async def admin_login(data: dict = Body(...)):
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력해 주세요.")

    admin_username = os.getenv("ADMIN_USERNAME", "winkey")
    admin_password = os.getenv("ADMIN_PASSWORD", "!Korea1004")

    # 1) 환경변수(또는 기본값) 관리자 계정 우선 확인
    if username == admin_username and password == admin_password:
        return {
            "success": True,
            "message": "로그인 성공",
            "admin_id": username
        }

    # 2) DB 관리자 계정(role >= 100) 확인
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT member_id, member_password, role
                FROM training_member
                WHERE member_id = %s AND role >= 100
                ORDER BY create_date DESC
                LIMIT 1
                """,
                (username,)
            )
            admin_user = cursor.fetchone()

            if not admin_user:
                raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 일치하지 않습니다.")

            stored_password = (admin_user.get("member_password") or "").strip()
            password_sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()

            if stored_password and (password == stored_password or password_sha256 == stored_password):
                return {
                    "success": True,
                    "message": "로그인 성공",
                    "admin_id": username
                }

            raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 일치하지 않습니다.")
    finally:
        conn.close()

@app.post("/api/supervisor/login")
async def supervisor_login(data: dict = Body(...)):
    """감독자 로그인: 트레이닝 키와 이름으로 인증"""
    training_key = (data.get("training_key") or "").strip()
    supervisor_name = (data.get("supervisor_name") or "").strip()

    if not training_key or not supervisor_name:
        raise HTTPException(status_code=400, detail="과정 키와 이름을 입력해 주세요.")

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1) 과정이 존재하는지 확인
            cursor.execute(
                "SELECT training_key, course_name FROM training WHERE training_key = %s",
                (training_key,)
            )
            training = cursor.fetchone()
            
            if not training:
                raise HTTPException(status_code=401, detail="유효하지 않은 과정 키입니다.")
            
            # 2) 감독자 권한 확인
            cursor.execute(
                """
                SELECT id, supervisor_name, is_active 
                FROM training_supervisors 
                WHERE training_key = %s AND supervisor_name = %s AND is_active = 1
                """,
                (training_key, supervisor_name)
            )
            supervisor = cursor.fetchone()

            if not supervisor:
                raise HTTPException(status_code=401, detail="감독자 권한이 없습니다. 관리자에게 문의하세요.")

            return {
                "success": True,
                "message": "로그인 성공",
                "role": "supervisor",
                "training_key": training_key,
                "supervisor_name": supervisor_name,
                "course_name": training.get("course_name")
            }
    finally:
        conn.close()

@app.get("/admin/lab")
async def lab_page():
    return FileResponse("templates/lab.html")

@app.get("/admin/lab-test")
async def lab_test_page():
    return FileResponse("templates/lab_test.html")

@app.get("/admin/lab_content")
async def lab_content_page():
    return FileResponse("templates/lab_content.html")

@app.get("/supervisor/monitoring")
async def supervisor_monitoring_page():
    return FileResponse("templates/supervisor.html")



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
            users = [{"member_id": row['member_id'], "member_name": row['member_name'], "role": row['role'], "create_date": format_kst(row['create_date'])} for row in result]
        return users
    finally:
        conn.close()

@app.get("/api/admin/users/course/{training_key}")
async def get_users_by_course(training_key: str):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 사용자 정보와 마지막으로 본 콘텐츠 정보를 함께 조회
            # MySQL 5.7 호환을 위해 ROW_NUMBER() 대신 서브쿼리 사용
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
                    tll.create_date as last_view_date,
                    ts.id as supervisor_id
                FROM training_member tm
                LEFT JOIN (
                    SELECT t1.member_key, t1.lab_id, t1.content_id, t1.create_date
                    FROM training_lab_log t1
                    INNER JOIN (
                        SELECT member_key, MAX(create_date) as max_date
                        FROM training_lab_log
                        WHERE training_key = %s
                        GROUP BY member_key
                    ) t2 ON t1.member_key = t2.member_key AND t1.create_date = t2.max_date
                    WHERE t1.training_key = %s
                ) tll ON tm.member_key = tll.member_key
                LEFT JOIN training_lab_contents tlc ON tll.lab_id = tlc.lab_id AND tll.content_id = tlc.content_id AND tlc.training_key = %s
                LEFT JOIN training_lab tl ON tll.lab_id = tl.lab_id AND tl.training_key = %s
                LEFT JOIN training_supervisors ts ON tm.training_key = ts.training_key AND tm.member_name = ts.supervisor_name AND ts.is_active = 1
                WHERE tm.training_key = %s 
                ORDER BY tm.create_date DESC
            """, (training_key, training_key, training_key, training_key, training_key))
            result = cursor.fetchall()
            
            users = []
            for row in result:
                last_content_info = ""
                if row['lab_id'] and row['content_id']:
                    last_content_info = f"{row['lab_name']} - {row['lab_content_subject']}"
                    if row['last_view_date']:
                        last_content_info += f" ({format_kst(row['last_view_date'])})"
                
                users.append({
                    "member_id": row['member_id'], 
                    "member_name": row['member_name'], 
                    "role": row['role'], 
                    "create_date": format_kst(row['create_date']),
                    "last_content": last_content_info,
                    "is_supervisor": row['supervisor_id'] is not None
                })
        return users
    except Exception as e:
        print(f"get_users_by_course 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"사용자 목록 조회 중 오류가 발생했습니다: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: str):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM training_member WHERE member_id = %s", (user_id,))
        conn.commit()
        return {"message": "User deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")
    finally:
        conn.close()

# 감독자 관리 API
@app.get("/api/admin/supervisors/{training_key}")
async def get_supervisors(training_key: str):
    """특정 과정의 감독자 목록 조회"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, supervisor_name, is_active, create_date 
                FROM training_supervisors 
                WHERE training_key = %s 
                ORDER BY create_date DESC
                """,
                (training_key,)
            )
            result = cursor.fetchall()
            supervisors = [
                {
                    "id": row['id'],
                    "supervisor_name": row['supervisor_name'],
                    "is_active": row['is_active'],
                    "create_date": format_kst(row['create_date'])
                }
                for row in result
            ]
        return supervisors
    finally:
        conn.close()

@app.post("/api/admin/supervisors")
async def add_supervisor(data: dict = Body(...)):
    """감독자 추가"""
    training_key = data.get("training_key")
    supervisor_name = data.get("supervisor_name")
    
    if not training_key or not supervisor_name:
        raise HTTPException(status_code=400, detail="과정 키와 감독자 이름을 입력해주세요.")
    
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO training_supervisors (training_key, supervisor_name, is_active) 
                    VALUES (%s, %s, 1)
                    """,
                    (training_key, supervisor_name)
                )
                conn.commit()
                return {"message": "감독자가 추가되었습니다."}
            except pymysql.err.IntegrityError:
                raise HTTPException(status_code=400, detail="이미 등록된 감독자입니다.")
    finally:
        conn.close()

@app.delete("/api/admin/supervisors/{supervisor_id}")
async def delete_supervisor(supervisor_id: int):
    """감독자 삭제"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM training_supervisors WHERE id = %s", (supervisor_id,))
            conn.commit()
        return {"message": "감독자가 삭제되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"감독자 삭제 실패: {str(e)}")
    finally:
        conn.close()

@app.post("/api/admin/assign-supervisor")
async def assign_supervisor(data: dict = Body(...)):
    """사용자를 운영자(감독자)로 지정"""
    training_key = data.get("training_key")
    member_name = data.get("member_name")
    
    if not training_key or not member_name:
        raise HTTPException(status_code=400, detail="과정 키와 사용자 이름을 입력해주세요.")
    
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1. 사용자가 존재하는지 확인
            cursor.execute(
                "SELECT member_id FROM training_member WHERE training_key = %s AND member_name = %s",
                (training_key, member_name)
            )
            member = cursor.fetchone()
            if not member:
                raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
            
            # 2. 이미 감독자인지 확인
            cursor.execute(
                "SELECT id FROM training_supervisors WHERE training_key = %s AND supervisor_name = %s",
                (training_key, member_name)
            )
            existing = cursor.fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="이미 운영자로 지정된 사용자입니다.")
            
            # 3. 감독자로 추가
            cursor.execute(
                "INSERT INTO training_supervisors (training_key, supervisor_name, is_active) VALUES (%s, %s, 1)",
                (training_key, member_name)
            )
            conn.commit()
            return {"message": "운영자로 지정되었습니다.", "success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"운영자 지정 실패: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/admin/remove-supervisor/{training_key}/{member_name}")
async def remove_supervisor(training_key: str, member_name: str):
    """사용자의 운영자 권한 해제"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM training_supervisors WHERE training_key = %s AND supervisor_name = %s",
                (training_key, member_name)
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="운영자 권한이 없습니다.")
            conn.commit()
            return {"message": "운영자 권한이 해제되었습니다.", "success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"운영자 권한 해제 실패: {str(e)}")
    finally:
        conn.close()

@app.get("/api/admin/courses")
async def get_courses():
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT training_key, course_name, course_content, max_member, create_date, training_status, is_public FROM training ORDER BY create_date DESC")
            result = cursor.fetchall()
            courses = [
                {
                    "training_key": row['training_key'],
                    "course_name": row['course_name'],
                    "course_content": row['course_content'],
                    "max_member": row['max_member'],
                    "create_date": format_kst(row['create_date']),
                    "training_status": row['training_status'],
                    "is_public": row['is_public'] if 'is_public' in row else 0
                }
                for row in result
            ]
        return courses
    finally:
        conn.close()

@app.get("/api/active-courses")
async def get_active_courses():
    """활성화된 과정 목록을 반환하는 API"""
    try:
        conn = get_mysql_conn()
        try:
            with conn.cursor() as cursor:
                # 활성화된 과정만 조회 (training_status = 20)
                cursor.execute("""
                    SELECT training_key, course_name, course_content, max_member, create_date, training_status, is_public 
                    FROM training 
                    WHERE training_status = 20
                    ORDER BY create_date DESC
                """)
                
                result = cursor.fetchall()
                courses = [
                    {
                        "training_key": row['training_key'],
                        "course_name": row['course_name'],
                        "course_content": row['course_content'],
                        "max_member": row['max_member'],
                        "create_date": format_kst(row['create_date']),
                        "training_status": row['training_status'],
                        "is_public": row['is_public'] if row['is_public'] else 0
                    }
                    for row in result
                ]
            return courses
        finally:
            conn.close()
    except Exception as e:
        print(f"데이터베이스 오류: {str(e)}")
        # 오류 발생 시 빈 목록 반환
        return []

@app.get("/api/admin/courses/{training_key}")
async def get_course(training_key: str):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT training_key, course_name, course_content, max_member, create_date, training_status, is_public FROM training WHERE training_key = %s", (training_key,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="과정을 찾을 수 없습니다.")
            return {
                "training_key": row['training_key'],
                "course_name": row['course_name'],
                "course_content": row['course_content'],
                "max_member": row['max_member'],
                "create_date": format_kst(row['create_date']),
                "training_status": row['training_status'],
                "is_public": row['is_public'] if 'is_public' in row else 0
            }
    finally:
        conn.close()

@app.post("/api/admin/courses")
async def add_course(data: dict = Body(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 6자리 랜덤 숫자 생성 (중복 확인)
            max_attempts = 100
            training_key = None
            for _ in range(max_attempts):
                training_key = f"{random.randint(0, 999999):06d}"
                cursor.execute("SELECT 1 FROM training WHERE training_key = %s", (training_key,))
                exists = cursor.fetchone()
                if not exists:
                    break
            else:
                raise HTTPException(status_code=500, detail="트레이닝 키를 생성할 수 없습니다. 잠시 후 다시 시도해주세요.")
            
            now = now_kst_naive()
            try:
                cursor.execute(
                    "INSERT INTO training (training_key, course_name, course_content, max_member, create_date, training_status, is_public) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        training_key,
                        data.get("course_name"),
                        data.get("course_content", ""),
                        data.get("max_member"),
                        now,
                        data.get("training_status"),
                        data.get("is_public", 0)  # 기본값을 비공개(0)로 설정
                    )
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"코스 추가 실패: {str(e)}")
        conn.commit()
        return {"message": "코스가 추가되었습니다."}
    finally:
        conn.close()

@app.put("/api/admin/courses/{training_key}")
async def update_course(training_key: str, data: dict = Body(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "UPDATE training SET course_name=%s, course_content=%s, max_member=%s, training_status=%s, is_public=%s WHERE training_key=%s",
                    (
                        data.get("course_name"),
                        data.get("course_content", ""),
                        int(data.get("max_member")),
                        data.get("training_status"),
                        data.get("is_public", 0),
                        training_key
                    )
                )
                
                # 과정의 공개 상태가 변경되면 해당 과정의 모든 랩과 콘텐츠의 공개 상태도 업데이트
                is_public = data.get("is_public", 0)
                cursor.execute(
                    "UPDATE training_lab SET is_public=%s WHERE training_key=%s",
                    (is_public, training_key)
                )
                cursor.execute(
                    "UPDATE training_lab_contents SET is_public=%s WHERE training_key=%s",
                    (is_public, training_key)
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"코스 수정 실패: {str(e)}")
        conn.commit()
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
        conn.commit()
        return {"message": "코스가 삭제되었습니다."}
    finally:
        conn.close()


@app.get("/api/admin/test-categories")
@app.get("/api/admin/test-categories/")
async def get_test_categories():
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, category_name, description, is_active, create_date, update_date
                FROM test_categories
                ORDER BY create_date DESC, id DESC
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "category_name": row["category_name"],
                    "description": row["description"] or "",
                    "is_active": int(row["is_active"] or 0),
                    "create_date": format_kst(row["create_date"]),
                    "update_date": format_kst(row["update_date"]),
                }
                for row in rows
            ]
    finally:
        conn.close()


@app.get("/api/admin/test-categories/{category_id}")
@app.get("/api/admin/test-categories/{category_id}/")
async def get_test_category(category_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, category_name, description, is_active, create_date, update_date
                FROM test_categories
                WHERE id = %s
                """,
                (category_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="테스트 종목을 찾을 수 없습니다.")
            return {
                "id": row["id"],
                "category_name": row["category_name"],
                "description": row["description"] or "",
                "is_active": int(row["is_active"] or 0),
                "create_date": format_kst(row["create_date"]),
                "update_date": format_kst(row["update_date"]),
            }
    finally:
        conn.close()


@app.post("/api/admin/test-categories")
@app.post("/api/admin/test-categories/")
async def add_test_category(data: dict = Body(...)):
    category_name = (data.get("category_name") or "").strip()
    description = (data.get("description") or "").strip()
    is_active = 1 if int(data.get("is_active", 1)) == 1 else 0

    if not category_name:
        raise HTTPException(status_code=400, detail="테스트 종목명을 입력해주세요.")

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO test_categories (category_name, description, is_active)
                    VALUES (%s, %s, %s)
                    """,
                    (category_name, description, is_active)
                )
                conn.commit()
            except pymysql.err.IntegrityError:
                raise HTTPException(status_code=400, detail="이미 존재하는 테스트 종목명입니다.")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"테스트 종목 추가 실패: {str(e)}")
        return {"message": "테스트 종목이 추가되었습니다."}
    finally:
        conn.close()


@app.put("/api/admin/test-categories/{category_id}")
@app.put("/api/admin/test-categories/{category_id}/")
async def update_test_category(category_id: int, data: dict = Body(...)):
    category_name = (data.get("category_name") or "").strip()
    description = (data.get("description") or "").strip()
    is_active = 1 if int(data.get("is_active", 1)) == 1 else 0

    if not category_name:
        raise HTTPException(status_code=400, detail="테스트 종목명을 입력해주세요.")

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM test_categories WHERE id = %s", (category_id,))
            exists = cursor.fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="테스트 종목을 찾을 수 없습니다.")

            try:
                cursor.execute(
                    """
                    UPDATE test_categories
                    SET category_name = %s, description = %s, is_active = %s
                    WHERE id = %s
                    """,
                    (category_name, description, is_active, category_id)
                )
                conn.commit()
            except pymysql.err.IntegrityError:
                raise HTTPException(status_code=400, detail="이미 존재하는 테스트 종목명입니다.")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"테스트 종목 수정 실패: {str(e)}")

        return {"message": "테스트 종목이 수정되었습니다."}
    finally:
        conn.close()


@app.delete("/api/admin/test-categories/{category_id}")
@app.delete("/api/admin/test-categories/{category_id}/")
async def delete_test_category(category_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM test_categories WHERE id = %s", (category_id,))
            exists = cursor.fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="테스트 종목을 찾을 수 없습니다.")

            try:
                cursor.execute("DELETE FROM test_questions WHERE test_category_id = %s", (category_id,))
                cursor.execute("DELETE FROM test_categories WHERE id = %s", (category_id,))
                conn.commit()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"테스트 종목 삭제 실패: {str(e)}")

        return {"message": "테스트 종목이 삭제되었습니다."}
    finally:
        conn.close()


@app.get("/api/admin/question-categories")
@app.get("/api/admin/question-categories/")
async def get_question_categories():
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, category_name, description, is_active, create_date, update_date
                FROM question_categories
                ORDER BY create_date DESC, id DESC
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "category_name": row["category_name"],
                    "description": row["description"] or "",
                    "is_active": int(row["is_active"] or 0),
                    "create_date": format_kst(row["create_date"]),
                    "update_date": format_kst(row["update_date"]),
                }
                for row in rows
            ]
    finally:
        conn.close()


@app.get("/api/admin/question-categories/{question_category_id}")
@app.get("/api/admin/question-categories/{question_category_id}/")
async def get_question_category(question_category_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, category_name, description, is_active, create_date, update_date
                FROM question_categories
                WHERE id = %s
                """,
                (question_category_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="문제 카테고리를 찾을 수 없습니다.")
            return {
                "id": row["id"],
                "category_name": row["category_name"],
                "description": row["description"] or "",
                "is_active": int(row["is_active"] or 0),
                "create_date": format_kst(row["create_date"]),
                "update_date": format_kst(row["update_date"]),
            }
    finally:
        conn.close()


@app.post("/api/admin/question-categories")
@app.post("/api/admin/question-categories/")
async def add_question_category(data: dict = Body(...)):
    category_name = (data.get("category_name") or "").strip()
    description = (data.get("description") or "").strip()
    is_active = 1 if int(data.get("is_active", 1)) == 1 else 0

    if not category_name:
        raise HTTPException(status_code=400, detail="문제 카테고리명을 입력해주세요.")

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO question_categories (category_name, description, is_active)
                    VALUES (%s, %s, %s)
                    """,
                    (category_name, description, is_active)
                )
                conn.commit()
            except pymysql.err.IntegrityError:
                raise HTTPException(status_code=400, detail="이미 존재하는 문제 카테고리명입니다.")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"문제 카테고리 추가 실패: {str(e)}")
        return {"message": "문제 카테고리가 추가되었습니다."}
    finally:
        conn.close()


@app.put("/api/admin/question-categories/{question_category_id}")
@app.put("/api/admin/question-categories/{question_category_id}/")
async def update_question_category(question_category_id: int, data: dict = Body(...)):
    category_name = (data.get("category_name") or "").strip()
    description = (data.get("description") or "").strip()
    is_active = 1 if int(data.get("is_active", 1)) == 1 else 0

    if not category_name:
        raise HTTPException(status_code=400, detail="문제 카테고리명을 입력해주세요.")

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM question_categories WHERE id = %s", (question_category_id,))
            exists = cursor.fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="문제 카테고리를 찾을 수 없습니다.")

            try:
                cursor.execute(
                    """
                    UPDATE question_categories
                    SET category_name = %s, description = %s, is_active = %s
                    WHERE id = %s
                    """,
                    (category_name, description, is_active, question_category_id)
                )
                conn.commit()
            except pymysql.err.IntegrityError:
                raise HTTPException(status_code=400, detail="이미 존재하는 문제 카테고리명입니다.")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"문제 카테고리 수정 실패: {str(e)}")

        return {"message": "문제 카테고리가 수정되었습니다."}
    finally:
        conn.close()


@app.delete("/api/admin/question-categories/{question_category_id}")
@app.delete("/api/admin/question-categories/{question_category_id}/")
async def delete_question_category(question_category_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM question_categories WHERE id = %s", (question_category_id,))
            exists = cursor.fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="문제 카테고리를 찾을 수 없습니다.")

            try:
                cursor.execute(
                    "UPDATE test_questions SET question_category_id = NULL WHERE question_category_id = %s",
                    (question_category_id,)
                )
                cursor.execute("DELETE FROM question_categories WHERE id = %s", (question_category_id,))
                conn.commit()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"문제 카테고리 삭제 실패: {str(e)}")

        return {"message": "문제 카테고리가 삭제되었습니다."}
    finally:
        conn.close()


@app.get("/api/admin/test-categories/{category_id}/questions")
@app.get("/api/admin/test-categories/{category_id}/questions/")
async def get_test_questions(category_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, category_name FROM test_categories WHERE id = %s", (category_id,))
            category = cursor.fetchone()
            if not category:
                raise HTTPException(status_code=404, detail="테스트 종목을 찾을 수 없습니다.")

            cursor.execute(
                """
                SELECT
                    tq.id,
                    tq.test_category_id,
                    tq.question_category_id,
                    tq.course_code,
                    tq.question_number,
                    tq.question_type,
                    tq.question_category_name,
                    tq.question_title,
                    tq.question_text,
                    tq.image_urls_json,
                    tq.options_json,
                    tq.answer,
                    tq.is_active,
                    tq.create_date,
                    tq.update_date,
                    qc.category_name AS linked_question_category_name
                FROM test_questions tq
                LEFT JOIN question_categories qc ON tq.question_category_id = qc.id
                WHERE tq.test_category_id = %s
                ORDER BY tq.create_date DESC, tq.id DESC
                """,
                (category_id,)
            )
            rows = cursor.fetchall()
            return {
                "test_category": {
                    "id": category["id"],
                    "category_name": category["category_name"]
                },
                "questions": [
                    {
                        "id": row["id"],
                        "test_category_id": row["test_category_id"],
                        "question_category_id": row["question_category_id"],
                        "course_code": row.get("course_code") or "",
                        "question_number": row["question_number"],
                        "question_type": row.get("question_type") or "",
                        "question_category_name": row.get("linked_question_category_name") or row.get("question_category_name") or None,
                        "question_title": row["question_title"],
                        "question_text": row["question_text"] or "",
                        "image_urls": json.loads(row["image_urls_json"]) if row.get("image_urls_json") else [],
                        "options": json.loads(row["options_json"]) if row.get("options_json") else {},
                        "answer": row["answer"] or "",
                        "is_active": int(row["is_active"] or 0),
                        "create_date": format_kst(row["create_date"]),
                        "update_date": format_kst(row["update_date"]),
                    }
                    for row in rows
                ]
            }
    finally:
        conn.close()


@app.get("/api/admin/test-categories/{category_id}/question-summary")
@app.get("/api/admin/test-categories/{category_id}/question-summary/")
async def get_test_question_summary(category_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, category_name FROM test_categories WHERE id = %s",
                (category_id,)
            )
            category = cursor.fetchone()
            if not category:
                raise HTTPException(status_code=404, detail="테스트 종목을 찾을 수 없습니다.")

            cursor.execute(
                """
                SELECT
                    qc.id AS question_category_id,
                    qc.category_name AS question_category_name,
                    COUNT(tq.id) AS question_count
                FROM test_questions tq
                INNER JOIN question_categories qc ON tq.question_category_id = qc.id
                WHERE tq.test_category_id = %s AND tq.is_active = 1
                GROUP BY qc.id, qc.category_name
                ORDER BY qc.category_name ASC
                """,
                (category_id,)
            )
            summary_rows = cursor.fetchall()
            total_available = sum(int(row["question_count"] or 0) for row in summary_rows)
            return {
                "test_category": {
                    "id": category["id"],
                    "category_name": category["category_name"],
                },
                "available_question_count": total_available,
                "question_categories": [
                    {
                        "id": row["question_category_id"],
                        "category_name": row["question_category_name"],
                        "question_count": int(row["question_count"] or 0),
                    }
                    for row in summary_rows
                ]
            }
    finally:
        conn.close()


@app.get("/api/admin/generated-tests")
@app.get("/api/admin/generated-tests/")
async def get_generated_tests():
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    gt.id,
                    gt.test_category_id,
                    gt.generated_name,
                    gt.question_count,
                    gt.selected_category_ids_json,
                    gt.selected_category_names_json,
                    gt.is_random_order,
                    gt.is_full_selection,
                    gt.is_active,
                    gt.create_date,
                    gt.update_date,
                    tc.category_name AS test_category_name
                FROM generated_tests gt
                INNER JOIN test_categories tc ON gt.test_category_id = tc.id
                ORDER BY gt.create_date DESC, gt.id DESC
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "test_category_id": row["test_category_id"],
                    "test_category_name": row["test_category_name"],
                    "generated_name": row["generated_name"],
                    "question_count": int(row["question_count"] or 0),
                    "selected_category_ids": json.loads(row["selected_category_ids_json"]) if row.get("selected_category_ids_json") else [],
                    "selected_category_names": json.loads(row["selected_category_names_json"]) if row.get("selected_category_names_json") else [],
                    "is_random_order": int(row.get("is_random_order") or 0),
                    "is_full_selection": int(row.get("is_full_selection") or 0),
                    "is_active": int(row["is_active"] or 0),
                    "create_date": format_kst(row["create_date"]),
                    "update_date": format_kst(row["update_date"]),
                }
                for row in rows
            ]
    finally:
        conn.close()


@app.get("/api/admin/generated-tests/{generated_test_id}")
@app.get("/api/admin/generated-tests/{generated_test_id}/")
async def get_generated_test(generated_test_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    gt.id,
                    gt.test_category_id,
                    gt.generated_name,
                    gt.question_count,
                    gt.selected_category_ids_json,
                    gt.selected_category_names_json,
                    gt.questions_json,
                    gt.is_random_order,
                    gt.is_full_selection,
                    gt.is_active,
                    gt.create_date,
                    tc.category_name AS test_category_name
                FROM generated_tests gt
                INNER JOIN test_categories tc ON gt.test_category_id = tc.id
                WHERE gt.id = %s
                """,
                (generated_test_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="생성된 테스트를 찾을 수 없습니다.")

            return {
                "id": row["id"],
                "test_category_id": row["test_category_id"],
                "test_category_name": row["test_category_name"],
                "generated_name": row["generated_name"],
                "question_count": int(row["question_count"] or 0),
                "selected_category_ids": json.loads(row["selected_category_ids_json"]) if row.get("selected_category_ids_json") else [],
                "selected_category_names": json.loads(row["selected_category_names_json"]) if row.get("selected_category_names_json") else [],
                "questions": json.loads(row["questions_json"]) if row.get("questions_json") else [],
                "is_random_order": int(row.get("is_random_order") or 0),
                "is_full_selection": int(row.get("is_full_selection") or 0),
                "is_active": int(row["is_active"] or 0),
                "create_date": format_kst(row["create_date"]),
            }
    finally:
        conn.close()


@app.post("/api/admin/generated-tests")
@app.post("/api/admin/generated-tests/")
async def create_generated_test(data: dict = Body(...)):
    test_category_id = data.get("test_category_id")
    question_category_ids = data.get("question_category_ids") or []
    question_count = data.get("question_count")
    include_all_questions = bool(data.get("include_all_questions", False))
    random_order = bool(data.get("random_order", False))

    try:
        test_category_id = int(test_category_id)
    except Exception:
        raise HTTPException(status_code=400, detail="올바른 테스트 종목을 선택해주세요.")

    if not isinstance(question_category_ids, list):
        raise HTTPException(status_code=400, detail="문제 카테고리 값이 올바르지 않습니다.")

    try:
        normalized_category_ids = sorted({int(category_id) for category_id in question_category_ids if category_id is not None and str(category_id).strip() != ""})
    except Exception:
        raise HTTPException(status_code=400, detail="문제 카테고리 값이 올바르지 않습니다.")

    if not include_all_questions and not normalized_category_ids:
        raise HTTPException(status_code=400, detail="최소 1개 이상의 문제 카테고리를 선택해주세요.")

    if not include_all_questions:
        try:
            question_count = int(question_count)
        except Exception:
            raise HTTPException(status_code=400, detail="총 문항수는 숫자여야 합니다.")

        if question_count <= 0:
            raise HTTPException(status_code=400, detail="총 문항수는 1 이상이어야 합니다.")

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, category_name FROM test_categories WHERE id = %s AND is_active = 1",
                (test_category_id,)
            )
            test_category = cursor.fetchone()
            if not test_category:
                raise HTTPException(status_code=404, detail="활성 테스트 종목을 찾을 수 없습니다.")

            category_rows = []
            selected_category_names = []
            query_params = [test_category_id]
            category_filter_sql = ""

            if normalized_category_ids:
                placeholders = ", ".join(["%s"] * len(normalized_category_ids))
                cursor.execute(
                    f"""
                    SELECT id, category_name
                    FROM question_categories
                    WHERE id IN ({placeholders}) AND is_active = 1
                    ORDER BY category_name ASC
                    """,
                    tuple(normalized_category_ids)
                )
                category_rows = cursor.fetchall()
                if len(category_rows) != len(normalized_category_ids):
                    raise HTTPException(status_code=400, detail="선택한 문제 카테고리 중 사용할 수 없는 항목이 있습니다.")

                selected_category_names = [row["category_name"] for row in category_rows]
                category_filter_sql = f" AND tq.question_category_id IN ({placeholders})"
                query_params.extend(normalized_category_ids)
            elif include_all_questions:
                selected_category_names = ["전체"]

            cursor.execute(
                f"""
                SELECT
                    tq.id,
                    tq.question_number,
                    tq.question_type,
                    tq.question_title,
                    tq.question_text,
                    tq.question_category_id,
                    tq.question_category_name,
                    tq.image_urls_json,
                    tq.options_json,
                    tq.answer,
                    qc.category_name AS linked_question_category_name
                FROM test_questions tq
                LEFT JOIN question_categories qc ON tq.question_category_id = qc.id
                WHERE tq.test_category_id = %s
                  AND tq.is_active = 1
                  {category_filter_sql}
                ORDER BY
                    CASE WHEN tq.question_number IS NULL THEN 1 ELSE 0 END,
                    tq.question_number ASC,
                    tq.id ASC
                """,
                tuple(query_params)
            )
            question_rows = cursor.fetchall()
            if not question_rows:
                raise HTTPException(status_code=400, detail="선택한 조건에 맞는 활성 문제가 없습니다.")

            if include_all_questions:
                chosen_rows = list(question_rows)
                question_count = len(chosen_rows)
                if random_order:
                    random.shuffle(chosen_rows)
            else:
                if len(question_rows) < question_count:
                    raise HTTPException(
                        status_code=400,
                        detail=f"선택한 조건에서 생성 가능한 문항은 {len(question_rows)}개입니다."
                    )

                if random_order:
                    chosen_rows = random.sample(question_rows, question_count)
                else:
                    chosen_rows = question_rows[:question_count]

            question_snapshots = []
            for row in chosen_rows:
                raw_options = json.loads(row["options_json"]) if row.get("options_json") else {}
                question_type = (row.get("question_type") or "multiple_choice").strip().lower()
                if question_type == "yes_no":
                    options_out = {}
                    items_out = raw_options.get("items", [])
                elif question_type == "matching":
                    options_out = raw_options.get("options", [])
                    items_out = raw_options.get("items", [])
                else:
                    options_out = raw_options
                    items_out = []

                question_snapshots.append(
                    {
                        "id": row["id"],
                        "question_number": row.get("question_number"),
                        "question_type": question_type,
                        "question_title": row.get("question_title") or "",
                        "question_text": row.get("question_text") or "",
                        "question_category_id": row.get("question_category_id"),
                        "question_category_name": row.get("linked_question_category_name") or row.get("question_category_name") or "None",
                        "image_urls": json.loads(row["image_urls_json"]) if row.get("image_urls_json") else [],
                        "options": options_out,
                        "items": items_out,
                        "answer": row.get("answer") or "",
                    }
                )

            mode_label = "랜덤" if random_order else "순차"
            scope_label = "전체" if include_all_questions else "선택"
            generated_name = f"{test_category['category_name']} 테스트 ({scope_label}/{mode_label}) {now_kst().strftime('%Y-%m-%d %H:%M')}"

            cursor.execute(
                """
                INSERT INTO generated_tests (
                    test_category_id,
                    generated_name,
                    question_count,
                    selected_category_ids_json,
                    selected_category_names_json,
                    questions_json,
                    is_random_order,
                    is_full_selection,
                    is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
                """,
                (
                    test_category_id,
                    generated_name,
                    question_count,
                    json.dumps(normalized_category_ids, ensure_ascii=False),
                    json.dumps(selected_category_names, ensure_ascii=False),
                    json.dumps(question_snapshots, ensure_ascii=False),
                    1 if random_order else 0,
                    1 if include_all_questions else 0,
                )
            )
            generated_test_id = cursor.lastrowid
            conn.commit()

            return {
                "message": "테스트가 생성되었습니다.",
                "generated_test_id": generated_test_id,
                "generated_name": generated_name,
                "question_count": question_count,
            }
    finally:
        conn.close()


def build_generated_test_markdown(generated_name: str, test_category_name: str, questions: list) -> str:
    lines = [
        f"# {generated_name}",
        "",
        f"- 테스트 종목: {test_category_name}",
        f"- 문항 수: {len(questions)}",
        "",
        "---",
        "",
    ]

    for index, question in enumerate(questions, start=1):
        question_type = str(question.get("question_type") or "multiple_choice").strip().lower()
        question_text = (question.get("question_text") or question.get("question_title") or "").strip()
        question_category = question.get("question_category_name") or "None"

        lines.append(f"## {index}. {question_text}")
        lines.append(f"- 카테고리: {question_category}")
        lines.append(f"- 유형: {question_type}")

        if question_type == "yes_no":
            items = question.get("items") or []
            for sub_index, item in enumerate(items, start=1):
                sub_text = str(item.get("text") or "").strip()
                sub_answer = str(item.get("answer") or "").strip()
                lines.append(f"- {sub_index}) {sub_text} (정답: {sub_answer})")
        elif question_type == "matching":
            options = question.get("options") or []
            items = question.get("items") or []
            if options:
                lines.append("- 보기")
                for option_index, option_value in enumerate(options, start=1):
                    lines.append(f"  - {option_index}. {str(option_value)}")
            if items:
                lines.append("- 매칭 정답")
                for sub_index, item in enumerate(items, start=1):
                    sub_text = str(item.get("text") or "").strip()
                    sub_answer = str(item.get("answer") or "").strip()
                    lines.append(f"  - {sub_index}) {sub_text} -> {sub_answer}")
        else:
            options = question.get("options") or {}
            answer = str(question.get("answer") or "").strip()
            if isinstance(options, dict):
                for key in sorted(options.keys()):
                    lines.append(f"- {key}. {str(options.get(key) or '')}")
            lines.append(f"- 정답: {answer}")

        lines.append("")

    return "\n".join(lines).strip()


@app.post("/api/admin/generated-tests/{generated_test_id}/assign-to-lab")
@app.post("/api/admin/generated-tests/{generated_test_id}/assign-to-lab/")
async def assign_generated_test_to_lab(generated_test_id: int, data: dict = Body(...)):
    training_key = (data.get("training_key") or "").strip()
    lab_content_subject = (data.get("lab_content_subject") or "").strip()

    try:
        lab_content_status = int(data.get("lab_content_status", 1))
    except Exception:
        lab_content_status = 1

    if not training_key:
        raise HTTPException(status_code=400, detail="과정 키를 선택해주세요.")

    if lab_content_status not in (0, 1):
        lab_content_status = 1

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    gt.id,
                    gt.generated_name,
                    gt.questions_json,
                    tc.category_name AS test_category_name
                FROM generated_tests gt
                INNER JOIN test_categories tc ON gt.test_category_id = tc.id
                WHERE gt.id = %s
                """,
                (generated_test_id,)
            )
            generated_test = cursor.fetchone()
            if not generated_test:
                raise HTTPException(status_code=404, detail="생성된 테스트를 찾을 수 없습니다.")

            questions = json.loads(generated_test.get("questions_json") or "[]")
            if not questions:
                raise HTTPException(status_code=400, detail="할당할 문제 데이터가 없습니다.")

            # 과정 내 '테스트 센터' 랩이 없으면 마지막 순서로 생성
            cursor.execute(
                "SELECT lab_id, lab_name, is_public FROM training_lab WHERE training_key = %s AND lab_name = %s ORDER BY lab_id DESC LIMIT 1",
                (training_key, "테스트 센터")
            )
            lab = cursor.fetchone()
            created_test_center = False

            if not lab:
                cursor.execute(
                    "SELECT COALESCE(MAX(lab_id), 0) AS max_lab_id FROM training_lab WHERE training_key = %s",
                    (training_key,)
                )
                max_lab_row = cursor.fetchone()
                next_lab_id = int(max_lab_row.get("max_lab_id") or 0) + 1

                cursor.execute(
                    "SELECT COALESCE(is_public, 0) AS is_public FROM training WHERE training_key = %s",
                    (training_key,)
                )
                training_row = cursor.fetchone()
                is_public = int((training_row or {}).get("is_public") or 0)

                now = now_kst_naive()
                cursor.execute(
                    """
                    INSERT INTO training_lab (lab_id, training_key, lab_name, lab_content, lab_status, is_public, create_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        next_lab_id,
                        training_key,
                        "테스트 센터",
                        "자동 생성된 테스트 전용 랩",
                        1,
                        is_public,
                        now,
                    )
                )
                lab = {
                    "lab_id": next_lab_id,
                    "lab_name": "테스트 센터",
                    "is_public": is_public,
                }
                created_test_center = True

            lab_id = int(lab.get("lab_id"))

            cursor.execute(
                "SELECT MAX(content_id) as max_content_id, MAX(view_number) as max_view_number FROM training_lab_contents WHERE training_key = %s AND lab_id = %s",
                (training_key, lab_id)
            )
            max_result = cursor.fetchone()
            next_content_id = 1 if not max_result or max_result["max_content_id"] is None else int(max_result["max_content_id"]) + 1
            next_view_number = 1 if not max_result or max_result["max_view_number"] is None else int(max_result["max_view_number"]) + 1

            if not lab_content_subject:
                lab_content_subject = f"{generated_test['generated_name']}"

            lab_content = json.dumps(
                {
                    "content_kind": "generated_test_center",
                    "generated_test_id": generated_test_id,
                    "generated_name": generated_test.get("generated_name") or "",
                    "test_category_name": generated_test.get("test_category_name") or "",
                    "question_count": len(questions),
                },
                ensure_ascii=False,
            )

            now = now_kst_naive()
            cursor.execute(
                """
                INSERT INTO training_lab_contents (
                    training_key, lab_id, content_id, view_number, lab_content_subject, lab_content,
                    lab_content_type, lab_content_status, lab_content_create_date, is_public
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    training_key,
                    lab_id,
                    next_content_id,
                    next_view_number,
                    lab_content_subject,
                    lab_content,
                    4,
                    lab_content_status,
                    now,
                    int(lab.get("is_public") or 0),
                )
            )
            conn.commit()

            return {
                "message": "생성된 테스트가 랩 콘텐츠로 할당되었습니다.",
                "training_key": training_key,
                "lab_id": lab_id,
                "lab_name": lab.get("lab_name"),
                "created_test_center": created_test_center,
                "content_id": next_content_id,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"테스트 랩 할당 실패: {str(e)}")
    finally:
        conn.close()


@app.delete("/api/admin/generated-tests/{generated_test_id}")
@app.delete("/api/admin/generated-tests/{generated_test_id}/")
async def delete_generated_test(generated_test_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM generated_tests WHERE id = %s", (generated_test_id,))
            exists = cursor.fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="생성된 테스트를 찾을 수 없습니다.")

            cursor.execute("DELETE FROM generated_tests WHERE id = %s", (generated_test_id,))
            conn.commit()
            return {"message": "생성된 테스트가 삭제되었습니다."}
    finally:
        conn.close()


@app.post("/api/admin/test-questions/upload-image")
@app.post("/api/admin/test-questions/upload-image/")
async def upload_test_question_image(
    file: UploadFile = File(...),
    test_category_name: str = Form("None"),
    category_name: str = Form("None"),
    question_number: int = Form(...)
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="업로드할 이미지 파일이 필요합니다.")

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드할 수 있습니다.")

    ext = "png"
    if "/" in content_type:
        ext = content_type.split("/")[-1].lower() or "png"
    if ext == "jpeg":
        ext = "jpg"

    safe_course = sanitize_filename_part(test_category_name, "None")
    safe_category = sanitize_filename_part(category_name, "None")
    safe_number = sanitize_filename_part(str(question_number), "0")
    timestamp = now_kst_str("%Y%m%d%H%M%S")
    blob_name = f"{safe_course}-{safe_category}-{safe_number}-{timestamp}.{ext}"

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다.")

    blob_service_client = get_blob_service_client()
    container_name = get_blob_container_name("question")
    container_client = blob_service_client.get_container_client(container_name)
    try:
        container_client.create_container()
    except Exception:
        pass

    blob_client = container_client.get_blob_client(blob_name)
    try:
        if ContentSettings:
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )
        else:
            blob_client.upload_blob(data, overwrite=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 업로드 실패: {str(e)}")

    return {
        "message": "이미지가 업로드되었습니다.",
        "file_name": blob_name,
        "url": blob_client.url,
    }


@app.get("/api/admin/test-categories/{category_id}/questions/{question_id}")
@app.get("/api/admin/test-categories/{category_id}/questions/{question_id}/")
async def get_test_question(category_id: int, question_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, test_category_id, question_category_id, course_code, question_number, question_type, question_category_name, question_title, question_text, image_urls_json, options_json, answer, is_active, create_date, update_date
                FROM test_questions
                WHERE test_category_id = %s AND id = %s
                """,
                (category_id, question_id)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="문제를 찾을 수 없습니다.")

            _q_type = row.get("question_type") or ""
            _options_raw = json.loads(row["options_json"]) if row.get("options_json") else {}
            if _q_type == "yes_no":
                _items = _options_raw.get("items", [])
                _options_out = {}
            elif _q_type == "matching":
                _items = _options_raw.get("items", [])
                _options_out = _options_raw.get("options", [])
            else:
                _items = []
                _options_out = _options_raw
            return {
                "id": row["id"],
                "test_category_id": row["test_category_id"],
                "question_category_id": row["question_category_id"],
                "course_code": row.get("course_code") or "",
                "question_number": row["question_number"],
                "question_type": _q_type,
                "question_category_name": row["question_category_name"] or None,
                "question_title": row["question_title"],
                "question_text": row["question_text"] or "",
                "image_urls": json.loads(row["image_urls_json"]) if row.get("image_urls_json") else [],
                "options": _options_out,
                "items": _items,
                "answer": row["answer"] or "",
                "question_payload": {
                    "course_code": row.get("course_code") or "",
                    "question_number": row["question_number"],
                    "question_type": _q_type,
                    "question": row["question_text"] or row["question_title"] or "",
                    "image_urls": json.loads(row["image_urls_json"]) if row.get("image_urls_json") else [],
                    "options": _options_out,
                    "items": _items,
                    "answer": row["answer"] or ""
                },
                "is_active": int(row["is_active"] or 0),
                "create_date": format_kst(row["create_date"]),
                "update_date": format_kst(row["update_date"]),
            }
    finally:
        conn.close()


@app.post("/api/admin/test-categories/{category_id}/questions")
@app.post("/api/admin/test-categories/{category_id}/questions/")
async def add_test_question(category_id: int, data: dict = Body(...)):
    raw_question_json = data.get("question_json")
    selected_question_category_id = data.get("question_category_id")
    course_code = (data.get("course_code") or "").strip()
    is_active = 1 if int(data.get("is_active", 1)) == 1 else 0

    parsed_question = None
    if isinstance(raw_question_json, str) and raw_question_json.strip():
        try:
            parsed_question = json.loads(raw_question_json)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"문제 JSON 파싱 실패: {str(e)}")
    elif isinstance(raw_question_json, dict):
        parsed_question = raw_question_json

    if parsed_question is None:
        parsed_question = data

    if not course_code:
        course_code = (parsed_question.get("course_code") or "").strip()

    question_number = parsed_question.get("question_number")
    if question_number in ("", None):
        question_number = None
    else:
        try:
            question_number = int(question_number)
        except Exception:
            raise HTTPException(status_code=400, detail="question_number는 숫자여야 합니다.")

    question_text = (parsed_question.get("question") or parsed_question.get("question_text") or "").strip()
    question_title = (parsed_question.get("question_title") or question_text or "").strip()
    image_urls = data.get("image_urls")
    if image_urls is None:
        image_urls = parsed_question.get("image_urls")
    if image_urls is None:
        image_urls = []
    if not isinstance(image_urls, list):
        raise HTTPException(status_code=400, detail="image_urls는 배열이어야 합니다.")
    image_urls = [str(u).strip() for u in image_urls if str(u).strip()]
    question_type = (parsed_question.get("question_type") or "").strip().lower() or "multiple_choice"
    if question_type == "yes_no":
        items = parsed_question.get("items") or []
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="yes_no 타입의 items는 배열이어야 합니다.")
        options = {"items": items}
        answer = None
    elif question_type == "matching":
        items = parsed_question.get("items") or []
        options_list = parsed_question.get("options") or []
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="matching 타입의 items는 배열이어야 합니다.")
        if not isinstance(options_list, list):
            raise HTTPException(status_code=400, detail="matching 타입의 options는 배열이어야 합니다.")
        options = {"items": items, "options": options_list}
        answer = None
    else:
        options = parsed_question.get("options") or {}
        answer = (parsed_question.get("answer") or "").strip() or None
        if not isinstance(options, dict):
            raise HTTPException(status_code=400, detail="options는 JSON 객체여야 합니다.")

    if not question_text:
        raise HTTPException(status_code=400, detail="question 값을 입력해주세요.")

    question_category_id = None
    question_category_name = None

    if selected_question_category_id in ("", None, "null"):
        selected_question_category_id = None
    elif selected_question_category_id is not None:
        try:
            selected_question_category_id = int(selected_question_category_id)
        except Exception:
            raise HTTPException(status_code=400, detail="선택한 문제 카테고리 값이 올바르지 않습니다.")

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM test_categories WHERE id = %s", (category_id,))
            category = cursor.fetchone()
            if not category:
                raise HTTPException(status_code=404, detail="테스트 종목을 찾을 수 없습니다.")

            if selected_question_category_id is not None:
                cursor.execute(
                    "SELECT id, category_name FROM question_categories WHERE id = %s",
                    (selected_question_category_id,)
                )
                question_category = cursor.fetchone()
                if not question_category:
                    raise HTTPException(status_code=404, detail="문제 카테고리를 찾을 수 없습니다.")
                question_category_id = question_category["id"]
                question_category_name = question_category["category_name"]

            try:
                cursor.execute(
                    """
                    INSERT INTO test_questions (test_category_id, question_category_id, course_code, question_number, question_category_name, question_title, question_text, image_urls_json, options_json, answer, is_active, question_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        category_id,
                        question_category_id,
                        course_code,
                        question_number,
                        question_category_name,
                        question_title,
                        question_text,
                        json.dumps(image_urls, ensure_ascii=False),
                        json.dumps(options, ensure_ascii=False),
                        answer,
                        is_active,
                        question_type
                    )
                )
                conn.commit()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"문제 추가 실패: {str(e)}")

        return {"message": "문제가 추가되었습니다."}
    finally:
        conn.close()


@app.put("/api/admin/test-categories/{category_id}/questions/{question_id}")
@app.put("/api/admin/test-categories/{category_id}/questions/{question_id}/")
async def update_test_question(category_id: int, question_id: int, data: dict = Body(...)):
    raw_question_json = data.get("question_json")
    selected_question_category_id = data.get("question_category_id")
    course_code = (data.get("course_code") or "").strip()
    is_active = 1 if int(data.get("is_active", 1)) == 1 else 0

    parsed_question = None
    if isinstance(raw_question_json, str) and raw_question_json.strip():
        try:
            parsed_question = json.loads(raw_question_json)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"문제 JSON 파싱 실패: {str(e)}")
    elif isinstance(raw_question_json, dict):
        parsed_question = raw_question_json

    if parsed_question is None:
        parsed_question = data

    if not course_code:
        course_code = (parsed_question.get("course_code") or "").strip()

    question_number = parsed_question.get("question_number")
    if question_number in ("", None):
        question_number = None
    else:
        try:
            question_number = int(question_number)
        except Exception:
            raise HTTPException(status_code=400, detail="question_number는 숫자여야 합니다.")

    question_text = (parsed_question.get("question") or parsed_question.get("question_text") or "").strip()
    question_title = (parsed_question.get("question_title") or question_text or "").strip()
    image_urls = data.get("image_urls")
    if image_urls is None:
        image_urls = parsed_question.get("image_urls")
    if image_urls is None:
        image_urls = []
    if not isinstance(image_urls, list):
        raise HTTPException(status_code=400, detail="image_urls는 배열이어야 합니다.")
    image_urls = [str(u).strip() for u in image_urls if str(u).strip()]
    question_type = (parsed_question.get("question_type") or "").strip().lower() or "multiple_choice"
    if question_type == "yes_no":
        items = parsed_question.get("items") or []
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="yes_no 타입의 items는 배열이어야 합니다.")
        options = {"items": items}
        answer = None
    elif question_type == "matching":
        items = parsed_question.get("items") or []
        options_list = parsed_question.get("options") or []
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="matching 타입의 items는 배열이어야 합니다.")
        if not isinstance(options_list, list):
            raise HTTPException(status_code=400, detail="matching 타입의 options는 배열이어야 합니다.")
        options = {"items": items, "options": options_list}
        answer = None
    else:
        options = parsed_question.get("options") or {}
        answer = (parsed_question.get("answer") or "").strip() or None
        if not isinstance(options, dict):
            raise HTTPException(status_code=400, detail="options는 JSON 객체여야 합니다.")

    if not question_text:
        raise HTTPException(status_code=400, detail="question 값을 입력해주세요.")

    question_category_id = None
    question_category_name = None

    if selected_question_category_id in ("", None, "null"):
        selected_question_category_id = None
    elif selected_question_category_id is not None:
        try:
            selected_question_category_id = int(selected_question_category_id)
        except Exception:
            raise HTTPException(status_code=400, detail="선택한 문제 카테고리 값이 올바르지 않습니다.")

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM test_questions WHERE test_category_id = %s AND id = %s",
                (category_id, question_id)
            )
            exists = cursor.fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="문제를 찾을 수 없습니다.")

            if selected_question_category_id is not None:
                cursor.execute(
                    "SELECT id, category_name FROM question_categories WHERE id = %s",
                    (selected_question_category_id,)
                )
                question_category = cursor.fetchone()
                if not question_category:
                    raise HTTPException(status_code=404, detail="문제 카테고리를 찾을 수 없습니다.")
                question_category_id = question_category["id"]
                question_category_name = question_category["category_name"]

            try:
                cursor.execute(
                    """
                    UPDATE test_questions
                    SET question_category_id = %s, course_code = %s, question_number = %s, question_category_name = %s, question_title = %s, question_text = %s, image_urls_json = %s, options_json = %s, answer = %s, is_active = %s, question_type = %s
                    WHERE test_category_id = %s AND id = %s
                    """,
                    (
                        question_category_id,
                        course_code,
                        question_number,
                        question_category_name,
                        question_title,
                        question_text,
                        json.dumps(image_urls, ensure_ascii=False),
                        json.dumps(options, ensure_ascii=False),
                        answer,
                        is_active,
                        question_type,
                        category_id,
                        question_id
                    )
                )
                conn.commit()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"문제 수정 실패: {str(e)}")

        return {"message": "문제가 수정되었습니다."}
    finally:
        conn.close()


@app.delete("/api/admin/test-categories/{category_id}/questions/{question_id}")
@app.delete("/api/admin/test-categories/{category_id}/questions/{question_id}/")
async def delete_test_question(category_id: int, question_id: int):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM test_questions WHERE test_category_id = %s AND id = %s",
                (category_id, question_id)
            )
            exists = cursor.fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="문제를 찾을 수 없습니다.")

            try:
                cursor.execute(
                    "DELETE FROM test_questions WHERE test_category_id = %s AND id = %s",
                    (category_id, question_id)
                )
                conn.commit()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"문제 삭제 실패: {str(e)}")

        return {"message": "문제가 삭제되었습니다."}
    finally:
        conn.close()

@app.post("/api/admin/courses/{source_training_key}/copy")
async def copy_course(source_training_key: str, data: dict = Body(...)):
    """기존 과정을 복사하여 새로운 과정을 생성하는 API"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1. 원본 과정 정보 조회
            cursor.execute("SELECT * FROM training WHERE training_key = %s", (source_training_key,))
            source_course = cursor.fetchone()
            if not source_course:
                raise HTTPException(status_code=404, detail="복사할 과정을 찾을 수 없습니다.")
            
            # 2. 새로운 training_key 생성 (6자리 랜덤, 중복 확인)
            now = now_kst_naive()
            new_training_key = None
            max_attempts = 100
            
            for _ in range(max_attempts):
                new_training_key = f"{random.randint(0, 999999):06d}"
                cursor.execute("SELECT 1 FROM training WHERE training_key = %s", (new_training_key,))
                exists = cursor.fetchone()
                if not exists:
                    break
            
            if not new_training_key:
                raise HTTPException(status_code=500, detail="트레이닝 키를 생성할 수 없습니다. 잠시 후 다시 시도해주세요.")
            
            # 3. 새로운 과정 생성
            new_course_name = data.get("new_course_name", f"{source_course['course_name']} (복사본)")
            new_max_member = data.get("max_member", source_course['max_member'])
            new_training_status = data.get("training_status", 10)  # 기본값: 준비중
            new_is_public = data.get("is_public", 0)  # 기본값: 비공개
            
            cursor.execute(
                "INSERT INTO training (training_key, course_name, course_content, max_member, create_date, training_status, is_public) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    new_training_key,
                    new_course_name,
                    source_course['course_content'],
                    new_max_member,
                    now,
                    new_training_status,
                    new_is_public
                )
            )
            
            # 4. 원본 과정의 랩들 복사
            cursor.execute("SELECT * FROM training_lab WHERE training_key = %s ORDER BY lab_id", (source_training_key,))
            source_labs = cursor.fetchall()
            
            lab_id_mapping = {}  # 원본 lab_id -> 새 lab_id 매핑
            
            for source_lab in source_labs:
                # 새로운 lab_id 생성 (해당 training_key에서 가장 큰 lab_id + 1)
                cursor.execute("SELECT MAX(lab_id) as max_lab_id FROM training_lab WHERE training_key = %s", (new_training_key,))
                result = cursor.fetchone()
                new_lab_id = 1 if not result or result['max_lab_id'] is None else int(result['max_lab_id']) + 1
                
                # 랩 복사
                cursor.execute(
                    "INSERT INTO training_lab (lab_id, training_key, lab_name, lab_content, lab_status, is_public, create_date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        new_lab_id,
                        new_training_key,
                        source_lab['lab_name'],
                        source_lab['lab_content'],
                        source_lab['lab_status'],
                        new_is_public,  # 새 과정의 공개 여부에 따라 설정
                        now
                    )
                )
                
                # lab_id 매핑 저장
                lab_id_mapping[source_lab['lab_id']] = new_lab_id
            
            # 5. 원본 과정의 랩 콘텐츠들 복사
            for source_lab in source_labs:
                source_lab_id = source_lab['lab_id']
                new_lab_id = lab_id_mapping[source_lab_id]
                
                cursor.execute("SELECT * FROM training_lab_contents WHERE training_key = %s AND lab_id = %s ORDER BY content_id", (source_training_key, source_lab_id))
                source_contents = cursor.fetchall()
                
                for source_content in source_contents:
                    # 새로운 content_id 생성
                    cursor.execute("SELECT MAX(content_id) as max_content_id FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (new_training_key, new_lab_id))
                    result = cursor.fetchone()
                    new_content_id = 1 if not result or result['max_content_id'] is None else int(result['max_content_id']) + 1
                    
                    # 콘텐츠 복사
                    cursor.execute(
                        "INSERT INTO training_lab_contents (training_key, lab_id, content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date, is_public) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            new_training_key,
                            new_lab_id,
                            new_content_id,
                            source_content['view_number'],
                            source_content['lab_content_subject'],
                            source_content['lab_content'],
                            source_content['lab_content_type'],
                            source_content['lab_content_status'],
                            now,
                            new_is_public  # 새 과정의 공개 여부에 따라 설정
                        )
                    )
            
            # 총 콘텐츠 개수 계산
            total_contents = 0
            for source_lab in source_labs:
                cursor.execute("SELECT COUNT(*) as count FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (source_training_key, source_lab['lab_id']))
                result = cursor.fetchone()
                total_contents += result['count'] if result else 0
            
            return {
                "message": "과정이 성공적으로 복사되었습니다.",
                "new_training_key": new_training_key,
                "new_course_name": new_course_name,
                "copied_labs": len(source_labs),
                "total_contents": total_contents
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"과정 복사 실패: {str(e)}")
    finally:
        if conn:
            conn.commit()
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
async def get_labs(training_key: str = Query(...)) -> List:
    
    # training_key 유효성 검사
    if not training_key or training_key.strip() == "":
        raise HTTPException(status_code=400, detail="유효하지 않은 과정 키입니다.")
    
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
                    l.is_public,
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
            
            labs = []
            for row in result:
                lab_dict = {
                    "lab_id": row['lab_id'],
                    "training_key": row['training_key'],
                    "lab_name": row['lab_name'],
                    "lab_content": row['lab_content'],
                    "lab_status": row['lab_status'],
                    "is_public": row['is_public'] if 'is_public' in row else 0,
                    "create_date": format_kst(row['create_date']),
                    "content_count": int(row['content_count'])
                }
                labs.append(lab_dict)
            return labs
    except HTTPException:
        # HTTPException은 그대로 전달
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"랩 목록을 불러오는데 실패했습니다: {str(e)}")
    finally:
        conn.close()

@app.get("/api/admin/labs/{lab_id}")
async def get_lab(lab_id: int, training_key: str = Query(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 특정 training_key와 lab_id로 조회
            cursor.execute("SELECT lab_id, training_key, lab_name, lab_content, lab_status, is_public, create_date FROM training_lab WHERE lab_id = %s AND training_key = %s", (lab_id, training_key))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"랩 ID {lab_id}를 찾을 수 없습니다.")
            
            lab = {
                "lab_id": result['lab_id'],
                "training_key": result['training_key'],
                "lab_name": result['lab_name'],
                "lab_content": result['lab_content'],
                "lab_status": result['lab_status'],
                "is_public": result['is_public'] if 'is_public' in result else 0,
                "create_date": format_kst(result['create_date'])
            }
            return lab
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"랩 정보를 불러오는데 실패했습니다: {str(e)}")
    finally:
        conn.close()

@app.post("/api/admin/labs")
async def add_lab(data: dict = Body(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 해당 training_key에서 가장 큰 lab_id 조회
            cursor.execute("SELECT MAX(lab_id) as max_lab_id FROM training_lab WHERE training_key = %s", (data.get("training_key"),))
            result = cursor.fetchone()
            current_max_id = result['max_lab_id'] if result and result['max_lab_id'] is not None else 0
            next_lab_id = current_max_id + 1
            
            # 해당 과정이 공개 과정인지 확인하여 is_public 값 결정
            cursor.execute("SELECT is_public FROM training WHERE training_key = %s", (data.get("training_key"),))
            training_result = cursor.fetchone()
            is_public = training_result['is_public'] if training_result else 0
            
            now = now_kst_naive()
            try:
                cursor.execute(
                    "INSERT INTO training_lab (lab_id, training_key, lab_name, lab_content, lab_status, is_public, create_date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        next_lab_id,
                        data.get("training_key"),
                        data.get("lab_name"),
                        data.get("lab_content"),
                        data.get("lab_status", 20),  # 기본값을 활성화(20)로 설정
                        is_public,  # 과정이 공개이면 랩도 공개로 설정
                        now
                    )
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"랩 추가 실패: {str(e)}")
        conn.commit()
        
        # 모니터링 이벤트 기록
        log_monitoring_event(
            training_key=data.get("training_key"),
            event_type="lab_add",
            event_category="lab",
            target_type="lab",
            target_id=str(next_lab_id),
            target_name=data.get("lab_name"),
            description=f"새로운 랩 '{data.get('lab_name')}'이(가) 추가되었습니다",
            details={
                "lab_id": next_lab_id,
                "lab_name": data.get("lab_name"),
                "lab_status": data.get("lab_status", 20),
                "is_public": is_public
            }
        )
        
        return {"message": "랩이 추가되었습니다.", "lab_id": next_lab_id}
    finally:
        conn.close()

@app.put("/api/admin/labs/{lab_id}")
async def update_lab(lab_id: int, data: dict = Body(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 먼저 해당 랩이 존재하는지 확인하고 랩명 조회 (training_key와 lab_id로 정확히 조회)
            training_key = data.get("training_key")
            if not training_key:
                raise HTTPException(status_code=400, detail="training_key가 필요합니다.")
            
            cursor.execute("SELECT lab_name FROM training_lab WHERE training_key = %s AND lab_id = %s", (training_key, lab_id))
            lab_exists = cursor.fetchone()
            if not lab_exists:
                raise HTTPException(status_code=404, detail=f"해당 과정에서 랩 ID {lab_id}를 찾을 수 없습니다.")
            
            lab_name = data.get("lab_name", lab_exists['lab_name'])
            
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
                    # 전체 업데이트 (랩명, 내용, 상태, 공개여부 모두)
                    cursor.execute(
                        "UPDATE training_lab SET lab_name=%s, lab_content=%s, lab_status=%s, is_public=%s WHERE lab_id=%s AND training_key=%s",
                        (
                            data.get("lab_name"),
                            data.get("lab_content"),
                            data.get("lab_status"),
                            data.get("is_public", 0),
                            lab_id,
                            data.get("training_key")
                        )
                    )
                
                # 업데이트된 행 수 확인
                if cursor.rowcount == 0:
                    raise HTTPException(status_code=400, detail="랩을 수정할 수 없습니다. training_key가 일치하지 않을 수 있습니다.")
                
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"랩 수정 실패: {str(e)}")
        conn.commit()
        
        # 모니터링 이벤트 기록  
        log_monitoring_event(
            training_key=data.get("training_key"),
            event_type="lab_edit",
            event_category="lab",
            target_type="lab",
            target_id=str(lab_id),
            target_name=lab_name,
            description=f"랩 '{lab_name}'이(가) 수정되었습니다",
            details={
                "lab_id": lab_id,
                "lab_name": lab_name,
                "lab_status": data.get("lab_status"),
                "status_only": "lab_status" in data and len(data) == 2
            }
        )
        
        return {"message": "랩이 수정되었습니다."}
    finally:
        conn.close()

@app.delete("/api/admin/labs/{lab_id}")
async def delete_lab(lab_id: int, training_key: str = Query(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 삭제 전 랩 정보 조회 (training_key와 lab_id로 정확히 조회)
            cursor.execute("SELECT training_key, lab_name FROM training_lab WHERE training_key = %s AND lab_id = %s", (training_key, lab_id))
            lab_info = cursor.fetchone()
            
            if not lab_info:
                raise HTTPException(status_code=404, detail="해당 과정에서 랩을 찾을 수 없습니다.")
            
            try:
                cursor.execute("DELETE FROM training_lab WHERE training_key = %s AND lab_id = %s", (training_key, lab_id))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"랩 삭제 실패: {str(e)}")
        conn.commit()
        
        # 모니터링 이벤트 기록
        if lab_info:
            log_monitoring_event(
                training_key=lab_info['training_key'],
                event_type="lab_delete",
                event_category="lab",
                target_type="lab",
                target_id=str(lab_id),
                target_name=lab_info['lab_name'],
                description=f"랩 '{lab_info['lab_name']}'이(가) 삭제되었습니다",
                details={
                    "lab_id": lab_id,
                    "lab_name": lab_info['lab_name']
                }
            )
        
        return {"message": "랩이 삭제되었습니다."}
    finally:
        conn.close()

@app.post("/api/admin/labs/{lab_id}/copy")
async def copy_lab(lab_id: int, source_training_key: str = Query(...), data: dict = Body(...)):
    """기존 랩을 다른 과정으로 복사하는 API"""
    target_training_key = data.get("target_training_key")
    
    if not target_training_key:
        raise HTTPException(status_code=400, detail="복사할 과정(target_training_key)이 필요합니다.")
    
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1. 원본 랩 정보 조회 (training_key와 lab_id로 정확히 조회)
            cursor.execute("SELECT * FROM training_lab WHERE training_key = %s AND lab_id = %s", (source_training_key, lab_id))
            source_lab = cursor.fetchone()
            
            if not source_lab:
                raise HTTPException(status_code=404, detail="복사할 랩을 찾을 수 없습니다.")
            
            # 2. 대상 과정이 존재하는지 확인
            cursor.execute("SELECT is_public FROM training WHERE training_key = %s", (target_training_key,))
            target_course = cursor.fetchone()
            
            if not target_course:
                raise HTTPException(status_code=404, detail="대상 과정을 찾을 수 없습니다.")
            
            # 3. 대상 과정에서 새로운 lab_id 생성
            cursor.execute("SELECT MAX(lab_id) as max_lab_id FROM training_lab WHERE training_key = %s", (target_training_key,))
            result = cursor.fetchone()
            new_lab_id = 1 if not result or result['max_lab_id'] is None else int(result['max_lab_id']) + 1
            
            now = now_kst_naive()
            target_is_public = target_course['is_public']
            
            # 4. 랩 복사
            cursor.execute(
                "INSERT INTO training_lab (lab_id, training_key, lab_name, lab_content, lab_status, is_public, create_date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    new_lab_id,
                    target_training_key,
                    source_lab['lab_name'],
                    source_lab['lab_content'],
                    source_lab['lab_status'],
                    target_is_public,
                    now
                )
            )
            
            # 5. 원본 랩의 콘텐츠들 복사 (정확한 training_key와 lab_id 사용)
            cursor.execute("SELECT * FROM training_lab_contents WHERE training_key = %s AND lab_id = %s ORDER BY view_number", (source_training_key, lab_id))
            source_contents = cursor.fetchall()
            
            copied_contents = 0
            for source_content in source_contents:
                # 새로운 content_id 생성
                cursor.execute("SELECT MAX(content_id) as max_content_id FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (target_training_key, new_lab_id))
                result = cursor.fetchone()
                new_content_id = 1 if not result or result['max_content_id'] is None else int(result['max_content_id']) + 1
                
                # 콘텐츠 복사
                cursor.execute(
                    "INSERT INTO training_lab_contents (training_key, lab_id, content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date, is_public) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        target_training_key,
                        new_lab_id,
                        new_content_id,
                        source_content['view_number'],
                        source_content['lab_content_subject'],
                        source_content['lab_content'],
                        source_content['lab_content_type'],
                        source_content['lab_content_status'],
                        now,
                        target_is_public
                    )
                )
                copied_contents += 1
            
            # 모니터링 이벤트 기록
            log_monitoring_event(
                training_key=target_training_key,
                event_type="lab_copy",
                event_category="lab",
                target_type="lab",
                target_id=str(new_lab_id),
                target_name=source_lab['lab_name'],
                description=f"랩 '{source_lab['lab_name']}'이(가) 과정({source_training_key})에서 과정({target_training_key})으로 복사되었습니다",
                details={
                    "source_training_key": source_training_key,
                    "source_lab_id": lab_id,
                    "target_training_key": target_training_key,
                    "new_lab_id": new_lab_id,
                    "lab_name": source_lab['lab_name'],
                    "copied_contents": copied_contents
                }
            )
            
            return {
                "message": "랩이 성공적으로 복사되었습니다.",
                "new_lab_id": new_lab_id,
                "target_training_key": target_training_key,
                "lab_name": source_lab['lab_name'],
                "copied_contents": copied_contents
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"랩 복사 실패: {str(e)}")
    finally:
        if conn:
            conn.commit()
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
                # 해당 랩의 감독자 여부 확인
                cursor.execute("""
                    SELECT ts.id FROM training_supervisors ts
                    WHERE ts.training_key = %s AND ts.supervisor_name = %s AND ts.is_active = 1
                """, (training_key, member_name))
                supervisor_result = cursor.fetchone()
                is_supervisor_of_lab = supervisor_result is not None
                
                lab_list.append({
                    "lab_id": r['lab_id'],
                    "lab_name": r['lab_name'],
                    "lab_content": r['lab_content'],
                    "lab_status": r['lab_status'],
                    "create_date": format_kst(r['create_date']),
                    "is_supervisor": is_supervisor_of_lab
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
    member_id = request.query_params.get("member_id")
    
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
            
            # member_id가 있으면 member_name 조회
            member_name = None
            if member_id:
                cursor.execute("""
                    SELECT member_name FROM training_member 
                    WHERE training_key = %s AND member_id = %s
                """, (training_key, member_id))
                member_result = cursor.fetchone()
                if member_result:
                    member_name = member_result['member_name']
            
            # 랩 목록 조회 (모든 랩)
            try:
                cursor.execute("""
                    SELECT lab_id, lab_name, lab_content, lab_status, create_date 
                    FROM training_lab 
                    WHERE training_key = %s
                    ORDER BY lab_id ASC
                """, (training_key,))
                labs_result = cursor.fetchall()
                
                
                lab_list = []
                for r in labs_result:
                    # member_name이 있으면 감독자 여부 확인
                    is_supervisor = False
                    if member_name:
                        cursor.execute("""
                            SELECT ts.id FROM training_supervisors ts
                            WHERE ts.training_key = %s AND ts.supervisor_name = %s AND ts.is_active = 1
                        """, (training_key, member_name))
                        supervisor_result = cursor.fetchone()
                        is_supervisor = supervisor_result is not None
                    
                    lab_list.append({
                        "lab_id": r['lab_id'],
                        "lab_name": r['lab_name'],
                        "lab_content": r['lab_content'],
                        "lab_status": r['lab_status'],
                        "create_date": format_kst(r['create_date']),
                        "is_supervisor": is_supervisor
                    })
                
            except Exception as e:
                lab_list = []
            
        return {
            "labs": lab_list, 
            "training_name": training_result['course_name'],
            "training_status": training_result['training_status']
        }
    except Exception as e:
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
        raise HTTPException(status_code=500, detail=f"사용자 진도 데이터를 불러오는데 실패했습니다: {str(e)}")
    finally:
        conn.close()

@app.post("/api/portal/log_content_view")
async def log_content_view(log: ContentViewLog):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 파라미터 데이터 타입 검증 및 변환
            try:
                training_key = str(log.training_key)
                member_id = str(log.member_id)
                lab_id = int(log.lab_id)
                content_id = int(log.content_id)
            except (ValueError, TypeError) as e:
                raise HTTPException(status_code=400, detail=f"파라미터 타입 오류: {str(e)}")
            
            # member_id로 member_key 조회
            cursor.execute("SELECT member_key, member_id, member_name FROM training_member WHERE training_key = %s AND member_id = %s", (training_key, member_id))
            member_result = cursor.fetchone()
            if not member_result:
                # 하위 호환: 과거 프론트에서 member_name이 member_id로 전달되던 케이스 대응
                cursor.execute(
                    "SELECT member_key, member_id, member_name FROM training_member WHERE training_key = %s AND member_name = %s",
                    (training_key, member_id)
                )
                member_result = cursor.fetchone()
                if not member_result:
                    # 디버그: 실제 데이터 확인
                    cursor.execute("SELECT member_id FROM training_member WHERE training_key = %s LIMIT 1", (training_key,))
                    sample = cursor.fetchone()
                    raise HTTPException(status_code=404, detail=f"사용자를 찾을 수 없습니다. training_key={training_key}, member_id={member_id} (존재하는 사용자: {sample['member_id'] if sample else 'None'})")
            
            member_key = member_result['member_key']
            actual_member_id = member_result['member_id']

            # 모니터링 이벤트는 항상 기록 (실시간 모니터링 용도)
            cursor.execute("SELECT member_name FROM training_member WHERE training_key = %s AND member_key = %s", (training_key, member_key))
            member_info = cursor.fetchone()
            cursor.execute("SELECT lab_content_subject FROM training_lab_contents WHERE training_key = %s AND lab_id = %s AND content_id = %s", (training_key, lab_id, content_id))
            content_info = cursor.fetchone()
            
            if member_info and content_info:
                log_monitoring_event(
                    training_key=training_key,
                    event_type="content_view",
                    event_category="content",
                    user_id=actual_member_id,
                    user_name=member_info['member_name'],
                    target_type="content",
                    target_id=str(content_id),
                    target_name=content_info['lab_content_subject'],
                    description=f"{member_info['member_name']} 사용자가 '{content_info['lab_content_subject']}' 콘텐츠를 조회했습니다",
                    details={
                        "member_name": member_info['member_name'],
                        "member_id": actual_member_id,
                        "lab_id": lab_id,
                        "content_id": content_id,
                        "content_subject": content_info['lab_content_subject']
                    }
                )

            # 로그 기록이 이미 존재하는지 확인 (중복 방지)
            cursor.execute("SELECT 1 FROM training_lab_log WHERE training_key = %s AND member_key = %s AND lab_id = %s AND content_id = %s", (training_key, member_key, lab_id, content_id))
            existing_log = cursor.fetchone()
            if existing_log:
                return {"message": "Content view already logged (monitoring recorded)"}

            # 로그 기록
            cursor.execute(
                "INSERT INTO training_lab_log (training_key, member_key, lab_id, content_id, create_date) VALUES (%s, %s, %s, %s, %s)",
                (
                    training_key,
                    member_key,
                    lab_id,
                    content_id,
                    now_kst_str('%Y-%m-%d %H:%M:%S')
                )
            )
            conn.commit()
            
            return {"message": "Content view logged successfully"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = f"콘텐츠 조회 기록 실패: training_key={log.training_key}, member_id={log.member_id}, lab_id={log.lab_id}, content_id={log.content_id}, error={str(e)}"
        print(f"ERROR: {error_msg}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        conn.close()

@app.get("/api/admin/monitoring-events")
async def get_monitoring_events(training_key: str = Query(...), limit: int = Query(50, le=100)):
    """실시간 모니터링 이벤트 조회 (특정 과정)"""
    try:
        # 특정 training_key의 최근 이벤트만 필터링
        events = [e for e in monitoring_events if e['training_key'] == training_key]
        # 최신 제한 개수만 반환 (이미 시간순으로 정렬되어 있음)
        events = events[-limit:] if len(events) > limit else events
        print(f"📊 [모니터링 API] training_key={training_key}, 전체 큐={len(monitoring_events)}, 필터링={len(events)}, 반환={len(events)}")
        return events
    except Exception as e:
        print(f"❌ [모니터링 API 오류] {str(e)}")
        import traceback
        traceback.print_exc()
        return []

@app.get("/api/admin/all-monitoring-events")
async def get_all_monitoring_events(limit: int = Query(50, le=100)):
    """모든 모니터링 이벤트 조회"""
    try:
        # 모든 이벤트를 시간순으로 반환 (deque는 이미 시간순)
        events = list(monitoring_events)
        # 최근 limit 개수만 반환
        events = events[-limit:] if len(events) > limit else events
        print(f"📊 [전체 모니터링 API] 전체 큐={len(monitoring_events)}, 반환={len(events)}")
        return events
    except Exception as e:
        print(f"❌ [전체 모니터링 API 오류] {str(e)}")
        import traceback
        traceback.print_exc()
        return []

@app.post("/api/admin/test-monitoring")
async def test_monitoring(training_key: str = "TEST", member_name: str = "테스트사용자"):
    """모니터링 테스트용 엔드포인트"""
    log_monitoring_event(training_key, "content_viewed", {
        "member_name": member_name,
        "lab_id": 1,
        "content_id": 1,
        "content_subject": "테스트 콘텐츠"
    })
    return {"message": "테스트 이벤트가 추가되었습니다", "total_events": len(monitoring_events)}

@app.get("/api/admin/lab_contents")
async def get_lab_contents(training_key: str = Query(...), lab_id: int = Query(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT training_key, lab_id, content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date FROM training_lab_contents WHERE training_key = %s AND lab_id = %s ORDER BY view_number ASC", (training_key, lab_id))
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
                    "lab_content_create_date": format_kst(row['lab_content_create_date'])
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
                "lab_content_create_date": format_kst(row['lab_content_create_date'])
            }
    finally:
        conn.close()

@app.post("/api/admin/lab_contents")
async def add_lab_content(data: dict = Body(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            content_type = normalize_lab_content_type(data.get("lab_content_type"))
            # content_id는 lab별로 1부터 시작하는 일련번호
            cursor.execute("SELECT MAX(content_id) as max_content_id FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (data.get("training_key"), data.get("lab_id")))
            result_content_id = cursor.fetchone()
            next_content_id = 1 if not result_content_id or result_content_id['max_content_id'] is None else int(result_content_id['max_content_id']) + 1

            # view_number는 해당 lab 내에서 MAX(view_number) + 1로 설정
            cursor.execute("SELECT MAX(view_number) as max_view_number FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (data.get("training_key"), data.get("lab_id")))
            result_view_number = cursor.fetchone()
            next_view_number = 1 if not result_view_number or result_view_number['max_view_number'] is None else int(result_view_number['max_view_number']) + 1

            now = now_kst_naive()
            # 해당 랩이 공개 랩인지 확인하여 is_public 값 결정
            cursor.execute("SELECT is_public FROM training_lab WHERE training_key = %s AND lab_id = %s", (data.get("training_key"), data.get("lab_id")))
            lab_result = cursor.fetchone()
            is_public = lab_result['is_public'] if lab_result else 0
            
            try:
                cursor.execute(
                    "INSERT INTO training_lab_contents (training_key, lab_id, content_id, view_number, lab_content_subject, lab_content, lab_content_type, lab_content_status, lab_content_create_date, is_public) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        data.get("training_key"),
                        data.get("lab_id"),
                        next_content_id,
                        next_view_number,
                        data.get("lab_content_subject"),
                        data.get("lab_content"),
                        content_type,
                        data.get("lab_content_status"),
                        now,
                        is_public
                    )
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"콘텐츠 추가 실패: {str(e)}")
        conn.commit()
        
        # 모니터링 이벤트 기록
        log_monitoring_event(
            training_key=data.get("training_key"),
            event_type="content_add",
            event_category="content",
            target_type="content",
            target_id=str(next_content_id),
            target_name=data.get("lab_content_subject"),
            description=f"새로운 콘텐츠 '{data.get('lab_content_subject')}'이(가) 추가되었습니다",
            details={
                "lab_id": data.get("lab_id"),
                "content_id": next_content_id,
                "subject": data.get("lab_content_subject"),
                "type": content_type,
                "status": data.get("lab_content_status"),
                "is_public": is_public
            }
        )
        
        return {"message": "콘텐츠가 추가되었습니다."}
    finally:
        conn.close()

@app.put("/api/admin/lab_contents/{content_id}")
async def update_lab_content(content_id: int, data: dict = Body(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            content_type = normalize_lab_content_type(data.get("lab_content_type"))
            try:
                cursor.execute(
                    "UPDATE training_lab_contents SET lab_content_subject=%s, lab_content=%s, lab_content_status=%s, lab_content_type=%s WHERE training_key=%s AND lab_id=%s AND content_id=%s",
                    (
                        data.get("lab_content_subject"),
                        data.get("lab_content"),
                        data.get("lab_content_status"),
                        content_type,
                        data.get("training_key"),
                        data.get("lab_id"),
                        content_id
                    )
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"콘텐츠 수정 실패: {str(e)}")
        conn.commit()
        
        # 모니터링 이벤트 기록
        log_monitoring_event(
            training_key=data.get("training_key"),
            event_type="content_edit",
            event_category="content",
            target_type="content",
            target_id=str(content_id),
            target_name=data.get("lab_content_subject"),
            description=f"콘텐츠 '{data.get('lab_content_subject')}'이(가) 수정되었습니다",
            details={
                "lab_id": data.get("lab_id"),
                "content_id": content_id,
                "subject": data.get("lab_content_subject"),
                "status": data.get("lab_content_status")
            }
        )
        
        return {"message": "콘텐츠가 수정되었습니다."}
    finally:
        conn.close()

@app.delete("/api/admin/lab_contents/{content_id}")
async def delete_lab_content(content_id: int, training_key: str = Query(...), lab_id: int = Query(...)):
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 삭제 전 콘텐츠 정보 조회
            cursor.execute("SELECT lab_content_subject FROM training_lab_contents WHERE training_key = %s AND lab_id = %s AND content_id = %s", (training_key, lab_id, content_id))
            content_info = cursor.fetchone()
            
            try:
                cursor.execute("DELETE FROM training_lab_contents WHERE training_key = %s AND lab_id = %s AND content_id = %s", (training_key, lab_id, content_id))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"콘텐츠 삭제 실패: {str(e)}")
        conn.commit()
        
        # 모니터링 이벤트 기록
        if content_info:
            log_monitoring_event(
                training_key=training_key,
                event_type="content_delete",
                event_category="content",
                target_type="content",
                target_id=str(content_id),
                target_name=content_info['lab_content_subject'],
                description=f"콘텐츠 '{content_info['lab_content_subject']}'이(가) 삭제되었습니다",
                details={
                    "lab_id": lab_id,
                    "content_id": content_id,
                    "subject": content_info['lab_content_subject']
                }
            )
        
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
            # 상태 변경 전 콘텐츠 정보 조회
            cursor.execute("SELECT lab_content_subject FROM training_lab_contents WHERE training_key=%s AND lab_id=%s AND content_id=%s", (training_key, lab_id, content_id))
            content_info = cursor.fetchone()
            
            try:
                cursor.execute(
                    "UPDATE training_lab_contents SET lab_content_status=%s WHERE training_key=%s AND lab_id=%s AND content_id=%s",
                    (new_status, training_key, lab_id, content_id)
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"콘텐츠 상태 업데이트 실패: {str(e)}")
        conn.commit()
        
        # 모니터링 이벤트 기록
        if content_info:
            log_monitoring_event(training_key, "content_status_changed", {
                "lab_id": lab_id,
                "content_id": content_id,
                "subject": content_info['lab_content_subject'],
                "new_status": "Active" if new_status == 1 else "Deactive"
            })
        
        return {"message": "콘텐츠 상태가 성공적으로 업데이트되었습니다."}
    finally:
        conn.close()

@app.put("/api/admin/lab_contents/{content_id}/move")
async def move_lab_content(
    content_id: int, 
    training_key: str = Query(...),
    lab_id: int = Query(...),
    data: dict = Body(...)
):
    new_lab_id = data.get("new_lab_id")
    if not new_lab_id:
        raise HTTPException(status_code=400, detail="new_lab_id가 필요합니다.")
    
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1. 현재 콘텐츠 정보 조회
            cursor.execute("SELECT training_key, lab_id FROM training_lab_contents WHERE content_id = %s AND training_key = %s AND lab_id = %s", (content_id, training_key, lab_id))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다.")
            
            # 2. 새로운 랩이 같은 과정에 속하는지 확인
            cursor.execute("SELECT COUNT(*) as cnt FROM training_lab WHERE training_key = %s AND lab_id = %s", (training_key, new_lab_id))
            result2 = cursor.fetchone()
            if not result2 or result2['cnt'] == 0:
                raise HTTPException(status_code=400, detail="해당 랩이 과정에 존재하지 않습니다.")
            
            # 3. 같은 랩으로 이동하려는 경우 체크
            if int(new_lab_id) == int(lab_id):
                return {"message": "이미 해당 랩에 있는 콘텐츠입니다."}
            
            # 4. 새로운 랩에서의 view_number 계산
            cursor.execute("SELECT MAX(view_number) as max_view_number FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (training_key, new_lab_id))
            result_view = cursor.fetchone()
            next_view_number = 1 if not result_view or result_view['max_view_number'] is None else int(result_view['max_view_number']) + 1
            
            # 5. 콘텐츠 이동 (lab_id와 view_number 업데이트)
            cursor.execute("UPDATE training_lab_contents SET lab_id = %s, view_number = %s WHERE content_id = %s AND training_key = %s AND lab_id = %s", (new_lab_id, next_view_number, content_id, training_key, lab_id))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="콘텐츠 이동에 실패했습니다.")
            
            conn.commit()
            return {"message": "콘텐츠가 성공적으로 이동되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"콘텐츠 이동 중 오류가 발생했습니다: {str(e)}")
    finally:
        conn.close()

@app.put("/api/admin/lab_contents/actions/bulk-move")
async def bulk_move_lab_contents(
    training_key: str = Query(...),
    lab_id: int = Query(...),
    data: BulkMoveContentRequest = Body(...)
):
    """여러 콘텐츠를 한번에 같은 과정의 다른 랩으로 이동"""
    content_ids = data.content_ids
    new_lab_id = data.new_lab_id
    target_training_key = data.target_training_key or training_key
    
    if not content_ids or len(content_ids) == 0:
        raise HTTPException(status_code=400, detail="이동할 콘텐츠를 선택해주세요.")
    
    if not new_lab_id:
        raise HTTPException(status_code=400, detail="new_lab_id가 필요합니다.")
    
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            if target_training_key != training_key:
                raise HTTPException(status_code=400, detail="다른 과정 선택 시 이동이 아닌 복사를 사용해주세요.")

            # 1. 대상 랩 존재 확인
            cursor.execute("SELECT is_public FROM training_lab WHERE training_key = %s AND lab_id = %s", (target_training_key, new_lab_id))
            target_lab = cursor.fetchone()
            if not target_lab:
                raise HTTPException(status_code=400, detail="해당 랩이 대상 과정에 존재하지 않습니다.")

            # 2. 같은 과정/같은 랩으로 이동하려는 경우 체크
            if target_training_key == training_key and int(new_lab_id) == int(lab_id):
                return {"message": "이미 해당 랩에 있는 콘텐츠입니다.", "moved_count": 0}

            # 3. 대상 랩의 시작 view_number 계산
            cursor.execute("SELECT MAX(view_number) as max_view_number FROM training_lab_contents WHERE training_key = %s AND lab_id = %s", (target_training_key, new_lab_id))
            result_view = cursor.fetchone()
            next_view_number = 1 if not result_view or result_view['max_view_number'] is None else int(result_view['max_view_number']) + 1
            moved_count = 0
            # 4. 각 콘텐츠를 이동
            for content_id in content_ids:
                # 콘텐츠가 현재 랩에 존재하는지 확인
                cursor.execute("SELECT content_id FROM training_lab_contents WHERE content_id = %s AND training_key = %s AND lab_id = %s", (content_id, training_key, lab_id))
                result = cursor.fetchone()
                
                if result:
                    # 동일 과정 내 이동
                    cursor.execute(
                        "UPDATE training_lab_contents SET lab_id = %s, view_number = %s WHERE content_id = %s AND training_key = %s AND lab_id = %s",
                        (new_lab_id, next_view_number, content_id, training_key, lab_id)
                    )
                    
                    if cursor.rowcount > 0:
                        moved_count += 1
                        next_view_number += 1
            
            if moved_count == 0:
                raise HTTPException(status_code=404, detail="이동할 수 있는 콘텐츠를 찾을 수 없습니다.")
            
            conn.commit()
            return {"message": f"{moved_count}개의 콘텐츠가 성공적으로 이동되었습니다.", "moved_count": moved_count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"콘텐츠 이동 중 오류가 발생했습니다: {str(e)}")
    finally:
        conn.close()

@app.post("/api/admin/lab_contents/actions/bulk-copy")
async def bulk_copy_lab_contents(
    training_key: str = Query(...),
    lab_id: int = Query(...),
    data: BulkCopyContentRequest = Body(...)
):
    """여러 콘텐츠를 한번에 다른 과정/랩으로 복사"""
    content_ids = data.content_ids
    target_training_key = data.target_training_key
    target_lab_id = data.target_lab_id

    if not content_ids:
        raise HTTPException(status_code=400, detail="복사할 콘텐츠를 선택해주세요.")

    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 대상 랩 확인
            cursor.execute(
                "SELECT lab_name, is_public FROM training_lab WHERE training_key = %s AND lab_id = %s",
                (target_training_key, target_lab_id)
            )
            target_lab = cursor.fetchone()
            if not target_lab:
                raise HTTPException(status_code=404, detail="대상 랩을 찾을 수 없습니다.")

            # 대상 랩의 시작 번호 계산
            cursor.execute(
                "SELECT MAX(content_id) as max_content_id, MAX(view_number) as max_view_number FROM training_lab_contents WHERE training_key = %s AND lab_id = %s",
                (target_training_key, target_lab_id)
            )
            max_result = cursor.fetchone()
            next_content_id = 1 if not max_result or max_result['max_content_id'] is None else int(max_result['max_content_id']) + 1
            next_view_number = 1 if not max_result or max_result['max_view_number'] is None else int(max_result['max_view_number']) + 1

            copied_count = 0
            for source_content_id in content_ids:
                cursor.execute(
                    "SELECT lab_content_subject, lab_content, lab_content_type, lab_content_status FROM training_lab_contents WHERE training_key = %s AND lab_id = %s AND content_id = %s",
                    (training_key, lab_id, source_content_id)
                )
                source_content = cursor.fetchone()
                if not source_content:
                    continue

                cursor.execute(
                    """
                    INSERT INTO training_lab_contents (
                        training_key, lab_id, content_id, view_number, lab_content_subject, lab_content,
                        lab_content_type, lab_content_status, lab_content_create_date, is_public
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        target_training_key,
                        target_lab_id,
                        next_content_id,
                        next_view_number,
                        source_content['lab_content_subject'],
                        source_content['lab_content'],
                        source_content['lab_content_type'],
                        source_content['lab_content_status'],
                        now_kst_naive(),
                        target_lab['is_public'] if target_lab.get('is_public') is not None else 0
                    )
                )

                copied_count += 1
                next_content_id += 1
                next_view_number += 1

            if copied_count == 0:
                raise HTTPException(status_code=404, detail="복사할 수 있는 콘텐츠를 찾을 수 없습니다.")

            conn.commit()
            return {"message": f"{copied_count}개의 콘텐츠가 성공적으로 복사되었습니다.", "copied_count": copied_count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"콘텐츠 복사 중 오류가 발생했습니다: {str(e)}")
    finally:
        conn.close()

@app.post("/api/admin/lab_contents/{content_id}/copy")
async def copy_lab_content(
    content_id: int,
    training_key: str = Query(...),
    lab_id: int = Query(...),
    data: dict = Body(...)
):
    """콘텐츠를 다른 과정의 다른 랩으로 복사"""
    target_training_key = data.get("target_training_key")
    target_lab_id = data.get("target_lab_id")
    
    if not target_training_key or not target_lab_id:
        raise HTTPException(status_code=400, detail="target_training_key와 target_lab_id가 필요합니다.")
    
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1. 원본 콘텐츠 정보 조회
            cursor.execute("""
                SELECT * FROM training_lab_contents 
                WHERE training_key = %s AND lab_id = %s AND content_id = %s
            """, (training_key, lab_id, content_id))
            source_content = cursor.fetchone()
            
            if not source_content:
                raise HTTPException(status_code=404, detail="원본 콘텐츠를 찾을 수 없습니다.")
            
            # 2. 대상 랩이 존재하는지 확인
            cursor.execute("""
                SELECT lab_name FROM training_lab 
                WHERE training_key = %s AND lab_id = %s
            """, (target_training_key, target_lab_id))
            target_lab = cursor.fetchone()
            
            if not target_lab:
                raise HTTPException(status_code=404, detail="대상 랩을 찾을 수 없습니다.")
            
            # 3. 대상 랩에서의 content_id 계산
            cursor.execute("""
                SELECT MAX(content_id) as max_content_id 
                FROM training_lab_contents 
                WHERE training_key = %s AND lab_id = %s
            """, (target_training_key, target_lab_id))
            result_content = cursor.fetchone()
            next_content_id = 1 if not result_content or result_content['max_content_id'] is None else int(result_content['max_content_id']) + 1
            
            # 4. 대상 랩에서의 view_number 계산
            cursor.execute("""
                SELECT MAX(view_number) as max_view_number 
                FROM training_lab_contents 
                WHERE training_key = %s AND lab_id = %s
            """, (target_training_key, target_lab_id))
            result_view = cursor.fetchone()
            next_view_number = 1 if not result_view or result_view['max_view_number'] is None else int(result_view['max_view_number']) + 1
            
            # 5. 대상 랩의 is_public 값 확인
            cursor.execute("""
                SELECT is_public FROM training_lab 
                WHERE training_key = %s AND lab_id = %s
            """, (target_training_key, target_lab_id))
            target_lab_info = cursor.fetchone()
            is_public = target_lab_info['is_public'] if target_lab_info else 0
            
            # 6. 콘텐츠 복사
            cursor.execute("""
                INSERT INTO training_lab_contents (
                    training_key, lab_id, content_id, view_number, lab_content_subject, lab_content,
                    lab_content_type, lab_content_status, lab_content_create_date, is_public
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                target_training_key,
                target_lab_id,
                                next_content_id,
                                next_view_number,
                source_content['lab_content_subject'],
                source_content['lab_content'],
                source_content['lab_content_type'],
                source_content['lab_content_status'],
                now_kst_naive(),
                is_public
            ))
            conn.commit()
            
            # 7. 모니터링 이벤트 기록
            log_monitoring_event(
                training_key=target_training_key,
                event_type="content_copy",
                event_category="content",
                target_type="content",
                target_id=str(next_content_id),
                target_name=source_content['lab_content_subject'],
                description=f"콘텐츠 '{source_content['lab_content_subject']}'이(가) 과정({training_key})에서 과정({target_training_key})의 랩({target_lab['lab_name']})으로 복사되었습니다",
                details={
                    "source_training_key": training_key,
                    "source_lab_id": lab_id,
                    "source_content_id": content_id,
                    "target_training_key": target_training_key,
                    "target_lab_id": target_lab_id,
                    "new_content_id": next_content_id
                }
            )
            
            return {
                "message": "콘텐츠가 성공적으로 복사되었습니다.",
                "content_subject": source_content['lab_content_subject'],
                "new_content_id": next_content_id,
                "target_lab_name": target_lab['lab_name']
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"콘텐츠 복사 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"콘텐츠 복사 실패: {str(e)}")
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
        raise HTTPException(status_code=500, detail=f"콘텐츠 순서 변경 중 오류가 발생했습니다: {str(e)}")
    finally:
        conn.close()

@app.get("/api/proxy-markdown")
async def proxy_markdown(url: str):
    """외부 URL에서 마크다운 콘텐츠를 가져오는 프록시 API"""
    try:
        # User-Agent 헤더를 추가하여 일부 서버의 차단 방지
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, timeout=15, headers=headers)
        resp.raise_for_status()
        
        # 텍스트 인코딩 자동 감지
        resp.encoding = resp.apparent_encoding or 'utf-8'
        
        return HTMLResponse(content=resp.text, status_code=200, media_type="text/plain; charset=utf-8")
    except requests.exceptions.Timeout:
        return HTMLResponse(content="URL 요청 시간이 초과되었습니다. (15초)", status_code=408)
    except requests.exceptions.HTTPError as e:
        return HTMLResponse(content=f"HTTP 오류: {e.response.status_code} - {e.response.reason}", status_code=400)
    except requests.exceptions.RequestException as e:
        return HTMLResponse(content=f"URL에서 마크다운을 불러올 수 없습니다: {str(e)}", status_code=400)
    except Exception as e:
        return HTMLResponse(content=f"마크다운 로드 중 오류 발생: {str(e)}", status_code=500)

@app.get("/public-training-portal")
async def public_training_portal():
    return FileResponse("templates/public_training_portal.html")

@app.get("/api/public-labs")
async def get_public_labs(training_key: str = Query(...)):
    """로그인 없이 접근 가능한 공개 랩 목록을 반환하는 API"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 먼저 해당 트레이닝이 존재하고 공개 상태인지 확인
            cursor.execute("""
                SELECT training_status, course_name, is_public
                FROM training 
                WHERE training_key = %s
            """, (training_key,))
            training_result = cursor.fetchone()
            
            if not training_result:
                return {"labs": [], "message": "트레이닝을 찾을 수 없습니다."}
            
            # 공개 트레이닝인지 확인 (is_public = 1)
            if not training_result.get('is_public'):
                return {"labs": [], "message": "이 트레이닝은 공개되지 않았습니다."}
            
            # 공개 랩 목록 조회 (lab_status = 20이고 is_public = 1인 랩만)
            try:
                cursor.execute("""
                    SELECT lab_id, lab_name, lab_content, lab_status, create_date, is_public
                    FROM training_lab 
                    WHERE training_key = %s AND lab_status = 20 AND is_public = 1
                    ORDER BY lab_id ASC
                """, (training_key,))
                labs_result = cursor.fetchall()
                
                lab_list = []
                for r in labs_result:
                    lab_list.append({
                        "lab_id": r['lab_id'],
                        "lab_name": r['lab_name'],
                        "lab_content": r['lab_content'],
                        "lab_status": r['lab_status'],
                        "create_date": format_kst(r['create_date']),
                        "is_public": r['is_public']
                    })
                
            except Exception as e:
                lab_list = []
            
        return {
            "labs": lab_list, 
            "training_name": training_result['course_name'],
            "training_status": training_result['training_status'],
            "is_public": training_result['is_public']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")
    finally:
        conn.close()

@app.get("/api/public-lab-contents")
async def get_public_lab_contents(training_key: str = Query(...), lab_id: int = Query(...)):
    """로그인 없이 접근 가능한 공개 랩의 콘텐츠 목록을 반환하는 API"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 해당 랩이 공개 랩인지 확인
            cursor.execute("""
                SELECT 1 FROM training_lab 
                WHERE training_key = %s AND lab_id = %s AND lab_status = 20 AND is_public = 1
            """, (training_key, lab_id))
            
            if not cursor.fetchone():
                raise HTTPException(status_code=403, detail="접근할 수 없는 랩입니다.")
            
            # 공개 랩의 모든 활성화된 콘텐츠 조회 (lab_content_status = 1인 콘텐츠만)
            cursor.execute("""
                SELECT content_id, view_number, lab_content_subject, lab_content, 
                       lab_content_type, lab_content_status, lab_content_create_date
                FROM training_lab_contents 
                WHERE training_key = %s AND lab_id = %s AND lab_content_status = 1
                ORDER BY view_number ASC
            """, (training_key, lab_id))
            
            result = cursor.fetchall()
            contents = [
                {
                    "content_id": row['content_id'],
                    "view_number": row['view_number'],
                    "lab_content_subject": row['lab_content_subject'],
                    "lab_content": row['lab_content'],
                    "lab_content_type": row['lab_content_type'],
                    "lab_content_status": row['lab_content_status'],
                    "lab_content_create_date": format_kst(row['lab_content_create_date'])
                }
                for row in result
            ]
            return contents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"콘텐츠 조회 실패: {str(e)}")
    finally:
        conn.close()

@app.get("/api/public-lab-content/{content_id}")
async def get_public_lab_content(content_id: int, training_key: str = Query(...), lab_id: int = Query(...)):
    """로그인 없이 접근 가능한 공개 랩의 특정 콘텐츠를 반환하는 API"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 해당 콘텐츠가 공개 랩의 활성화된 콘텐츠인지 확인
            cursor.execute("""
                SELECT content_id, view_number, lab_content_subject, lab_content, 
                       lab_content_type, lab_content_status, lab_content_create_date
                FROM training_lab_contents 
                WHERE training_key = %s AND lab_id = %s AND content_id = %s 
                      AND lab_content_status = 1
            """, (training_key, lab_id, content_id))
            
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없거나 접근할 수 없습니다.")
            
            return {
                "content_id": row['content_id'],
                "view_number": row['view_number'],
                "lab_content_subject": row['lab_content_subject'],
                "lab_content": row['lab_content'],
                "lab_content_type": row['lab_content_type'],
                "lab_content_status": row['lab_content_status'],
                "lab_content_create_date": format_kst(row['lab_content_create_date'])
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"콘텐츠 조회 실패: {str(e)}")
    finally:
        conn.close()

# SSE (Server-Sent Events) 엔드포인트
@app.get("/api/admin/monitoring/stream")
async def monitoring_stream(training_key: str = Query(...)):
    """실시간 모니터링 이벤트 스트림"""
    async def event_generator():
        try:
            # 초기 통계 전송
            conn = get_mysql_conn()
            try:
                with conn.cursor() as cursor:
                    # 전체 사용자 수
                    cursor.execute("SELECT COUNT(*) as cnt FROM training_member WHERE training_key = %s", (training_key,))
                    user_count_result = cursor.fetchone()
                    user_count = user_count_result['cnt'] if user_count_result else 0
                    
                    # 전체 랩 수
                    cursor.execute("SELECT COUNT(*) as cnt FROM training_lab WHERE training_key = %s", (training_key,))
                    lab_count_result = cursor.fetchone()
                    lab_count = lab_count_result['cnt'] if lab_count_result else 0
                    
                    # 전체 콘텐츠 수
                    cursor.execute("""
                        SELECT COUNT(*) as cnt FROM training_lab_contents tlc
                        JOIN training_lab tl ON tlc.lab_id = tl.lab_id
                        WHERE tl.training_key = %s
                    """, (training_key,))
                    content_count_result = cursor.fetchone()
                    content_count = content_count_result['cnt'] if content_count_result else 0
                    
                    initial_data = {
                        "type": "stats",
                        "data": {
                            "user_count": user_count,
                            "lab_count": lab_count,
                            "content_count": content_count
                        }
                    }
                    yield f"data: {json.dumps(initial_data)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            finally:
                conn.close()
            
            # 최근 이벤트 전송 (최근 10개만)
            recent_events = [e for e in list(monitoring_events) if e.get('training_key') == training_key][-10:]
            for event in recent_events:
                yield f"data: {json.dumps(event)}\n\n"
            last_event_index = len(monitoring_events)
            
            # 새 이벤트 체크 루프
            while True:
                await asyncio.sleep(2)  # 2초마다 체크
                
                # 새 이벤트 확인
                current_events = list(monitoring_events)
                if len(current_events) > last_event_index:
                    new_events = current_events[last_event_index:]
                    for event in new_events:
                        if event.get('training_key') == training_key:
                            yield f"data: {json.dumps(event)}\n\n"
                    last_event_index = len(current_events)
                else:
                    # Keep-alive
                    yield ": keep-alive\n\n"
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Stream error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# 폴링 방식 모니터링 엔드포인트
@app.get("/api/admin/monitoring/events")
async def get_monitoring_events(
    training_key: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
    since_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None)
):
    """
    폴링 방식으로 이벤트 로그를 조회하는 API
    
    Parameters:
    - training_key: 과정 키
    - limit: 가져올 이벤트 수 (기본값: 50, 최대: 500)
    - since_id: 이 ID 이후의 이벤트만 조회 (증분 폴링용)
    - category: 이벤트 카테고리 필터 (auth, user, lab, content 등)
    """
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 통계 정보 조회
            cursor.execute("SELECT COUNT(*) as cnt FROM training_member WHERE training_key = %s", (training_key,))
            user_count_result = cursor.fetchone()
            user_count = user_count_result['cnt'] if user_count_result else 0
            
            cursor.execute("SELECT COUNT(*) as cnt FROM training_lab WHERE training_key = %s", (training_key,))
            lab_count_result = cursor.fetchone()
            lab_count = lab_count_result['cnt'] if lab_count_result else 0
            
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM training_lab_contents tlc
                JOIN training_lab tl ON tlc.lab_id = tl.lab_id
                WHERE tl.training_key = %s
            """, (training_key,))
            content_count_result = cursor.fetchone()
            content_count = content_count_result['cnt'] if content_count_result else 0
            
            # 이벤트 로그 조회
            query = """
                SELECT id, training_key, event_type, event_category, user_id, user_name,
                       target_type, target_id, target_name, description, details, create_date
                FROM event_logs
                                WHERE training_key = %s
                                    AND create_date >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            """
            params = [training_key]
            
            if since_id:
                query += " AND id > %s"
                params.append(since_id)
            
            if category:
                query += " AND event_category = %s"
                params.append(category)
            
            query += " ORDER BY id DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            events = cursor.fetchall()
            
            # JSON 문자열을 파싱
            for event in events:
                if event.get('details') and isinstance(event['details'], str):
                    try:
                        event['details'] = json.loads(event['details'])
                    except:
                        pass
                event['create_date'] = format_kst(event['create_date'], '%Y-%m-%d %H:%M:%S')
            
            return {
                "success": True,
                "stats": {
                    "user_count": user_count,
                    "lab_count": lab_count,
                    "content_count": content_count
                },
                "events": events,
                "last_id": events[0]['id'] if events else None,
                "count": len(events)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이벤트 조회 실패: {str(e)}")
    finally:
        conn.close()

@app.get("/api/admin/monitoring/stats")
async def get_monitoring_stats(training_key: str = Query(...)):
    """모니터링 통계 정보 조회"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 사용자 수
            cursor.execute("SELECT COUNT(*) as cnt FROM training_member WHERE training_key = %s", (training_key,))
            user_count = cursor.fetchone()['cnt']
            
            # 랩 수
            cursor.execute("SELECT COUNT(*) as cnt FROM training_lab WHERE training_key = %s", (training_key,))
            lab_count = cursor.fetchone()['cnt']
            
            # 콘텐츠 수
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM training_lab_contents tlc
                JOIN training_lab tl ON tlc.lab_id = tl.lab_id
                WHERE tl.training_key = %s
            """, (training_key,))
            content_count = cursor.fetchone()['cnt']
            
            # 오늘의 이벤트 수
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM event_logs
                WHERE training_key = %s AND DATE(create_date) = CURDATE()
            """, (training_key,))
            today_events = cursor.fetchone()['cnt']
            
            # 카테고리별 이벤트 수 (최근 24시간)
            cursor.execute("""
                SELECT event_category, COUNT(*) as cnt
                FROM event_logs
                WHERE training_key = %s AND create_date >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                GROUP BY event_category
            """, (training_key,))
            category_counts = {row['event_category']: row['cnt'] for row in cursor.fetchall()}
            
            return {
                "user_count": user_count,
                "lab_count": lab_count,
                "content_count": content_count,
                "today_events": today_events,
                "category_counts": category_counts,
                "timestamp": now_kst().isoformat()
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")
    finally:
        conn.close()

# ============================================================
# 감독자(Supervisor) 모니터링 엔드포인트
# ============================================================

@app.get("/api/supervisor/monitoring/events")
async def get_supervisor_monitoring_events(
    training_key: str = Query(...),
    supervisor_name: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
    since_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None)
):
    """
    감독자용 폴링 방식 이벤트 로그 조회
    
    Parameters:
    - training_key: 과정 키
    - supervisor_name: 감독자 이름 (권한 확인용)
    - limit: 가져올 이벤트 수 (기본값: 50, 최대: 500)
    - since_id: 이 ID 이후의 이벤트만 조회 (증분 폴링용)
    - category: 이벤트 카테고리 필터
    """
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 1) 감독자 권한 확인
            cursor.execute(
                """
                SELECT id FROM training_supervisors 
                WHERE training_key = %s AND supervisor_name = %s AND is_active = 1
                """,
                (training_key, supervisor_name)
            )
            supervisor = cursor.fetchone()
            if not supervisor:
                raise HTTPException(status_code=403, detail="감독자 권한이 없습니다.")
            
            # 2) 통계 정보 조회
            cursor.execute("SELECT COUNT(*) as cnt FROM training_member WHERE training_key = %s", (training_key,))
            user_count_result = cursor.fetchone()
            user_count = user_count_result['cnt'] if user_count_result else 0
            
            cursor.execute("SELECT COUNT(*) as cnt FROM training_lab WHERE training_key = %s", (training_key,))
            lab_count_result = cursor.fetchone()
            lab_count = lab_count_result['cnt'] if lab_count_result else 0
            
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM training_lab_contents tlc
                JOIN training_lab tl ON tlc.lab_id = tl.lab_id
                WHERE tl.training_key = %s
            """, (training_key,))
            content_count_result = cursor.fetchone()
            content_count = content_count_result['cnt'] if content_count_result else 0
            
            # 3) 이벤트 로그 조회
            query = """
                SELECT id, training_key, event_type, event_category, user_id, user_name,
                       target_type, target_id, target_name, description, details, create_date
                FROM event_logs
                WHERE training_key = %s
                    AND create_date >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            """
            params = [training_key]
            
            if since_id:
                query += " AND id > %s"
                params.append(since_id)
            
            if category:
                query += " AND event_category = %s"
                params.append(category)
            
            query += " ORDER BY id DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            events = cursor.fetchall()
            
            # JSON 문자열을 파싱
            for event in events:
                if event.get('details') and isinstance(event['details'], str):
                    try:
                        event['details'] = json.loads(event['details'])
                    except:
                        pass
                event['create_date'] = format_kst(event['create_date'], '%Y-%m-%d %H:%M:%S')
            
            return {
                "success": True,
                "stats": {
                    "user_count": user_count,
                    "lab_count": lab_count,
                    "content_count": content_count
                },
                "events": events,
                "last_id": events[0]['id'] if events else None,
                "count": len(events)
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이벤트 조회 실패: {str(e)}")
    finally:
        conn.close()

@app.get("/api/supervisor/monitoring/stats")
async def get_supervisor_monitoring_stats(
    training_key: str = Query(...),
    supervisor_name: str = Query(...)
):
    """감독자용 모니터링 통계 정보 조회"""
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            # 감독자 권한 확인
            cursor.execute(
                """
                SELECT id FROM training_supervisors 
                WHERE training_key = %s AND supervisor_name = %s AND is_active = 1
                """,
                (training_key, supervisor_name)
            )
            supervisor = cursor.fetchone()
            if not supervisor:
                raise HTTPException(status_code=403, detail="감독자 권한이 없습니다.")
            
            # 사용자 수
            cursor.execute("SELECT COUNT(*) as cnt FROM training_member WHERE training_key = %s", (training_key,))
            user_count = cursor.fetchone()['cnt']
            
            # 랩 수
            cursor.execute("SELECT COUNT(*) as cnt FROM training_lab WHERE training_key = %s", (training_key,))
            lab_count = cursor.fetchone()['cnt']
            
            # 콘텐츠 수
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM training_lab_contents tlc
                JOIN training_lab tl ON tlc.lab_id = tl.lab_id
                WHERE tl.training_key = %s
            """, (training_key,))
            content_count = cursor.fetchone()['cnt']
            
            # 오늘의 이벤트 수
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM event_logs
                WHERE training_key = %s AND DATE(create_date) = CURDATE()
            """, (training_key,))
            today_events = cursor.fetchone()['cnt']
            
            # 카테고리별 이벤트 수 (최근 24시간)
            cursor.execute("""
                SELECT event_category, COUNT(*) as cnt
                FROM event_logs
                WHERE training_key = %s AND create_date >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                GROUP BY event_category
            """, (training_key,))
            category_counts = {row['event_category']: row['cnt'] for row in cursor.fetchall()}
            
            return {
                "user_count": user_count,
                "lab_count": lab_count,
                "content_count": content_count,
                "today_events": today_events,
                "category_counts": category_counts,
                "timestamp": now_kst().isoformat()
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)