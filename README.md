# Hello AI HTC Training Center

로그인이 필요 없는 공개 랩 과정과 기존의 로그인 기반 랩 과정을 모두 지원하는 통합 교육 플랫폼입니다.

## 주요 기능

### 🔓 공개 랩 과정 (새로 추가됨)
- **로그인 불필요**: 사용자 등록이나 로그인 없이 바로 학습 가능
- **무료 접근**: 모든 콘텐츠를 무료로 이용
- **공개 설정**: 관리자가 과정, 랩, 콘텐츠별로 공개/비공개 설정 가능

### 🔐 기존 랩 과정
- **로그인 기반**: 사용자 등록 및 로그인 필요
- **진도 추적**: 학습 진행 상황 및 콘텐츠 조회 기록
- **권한 관리**: 일반 사용자와 관리자 권한 구분

## 시스템 구조

### 데이터베이스 테이블
- `training`: 과정 정보 (공개 여부 포함)
- `training_lab`: 랩 정보 (공개 여부 포함)
- `training_lab_contents`: 콘텐츠 정보 (공개 여부 포함)
- `training_member`: 사용자 정보
- `training_lab_log`: 학습 로그 (공개 과정에는 기록되지 않음)

### API 엔드포인트

#### 공개 랩 과정용
- `GET /public-training-portal`: 공개 랩 과정 포털
- `GET /api/public-labs`: 공개 랩 목록 조회
- `GET /api/public-lab-contents`: 공개 랩 콘텐츠 목록 조회
- `GET /api/public-lab-content/{content_id}`: 공개 랩 콘텐츠 상세 조회

#### 기존 랩 과정용
- `GET /training-portal`: 로그인 기반 랩 과정 포털
- `GET /api/portal-labs`: 로그인 기반 랩 목록 조회
- `GET /api/portal/log_content_view`: 콘텐츠 조회 로그 기록

## 설치 및 설정

### 1. 데이터베이스 설정
```sql
-- 공개 랩 과정을 위한 is_public 필드 추가
ALTER TABLE training ADD COLUMN is_public TINYINT(1) DEFAULT 0 COMMENT '공개 여부 (1: 공개, 0: 비공개)';
ALTER TABLE training_lab ADD COLUMN is_public TINYINT(1) DEFAULT 0 COMMENT '공개 여부 (1: 공개, 0: 비공개)';
ALTER TABLE training_lab_contents ADD COLUMN is_public TINYINT(1) DEFAULT 0 COMMENT '공개 여부 (1: 공개, 0: 비공개)';

-- 기존 데이터는 모두 비공개로 설정
UPDATE training SET is_public = 0 WHERE is_public IS NULL;
UPDATE training_lab SET is_public = 0 WHERE is_public IS NULL;
UPDATE training_lab_contents SET is_public = 0 WHERE is_public IS NULL;
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정
```bash
# .env 파일 생성
MYSQL_HOST=your_mysql_host
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=your_mysql_database
```

### 4. 서버 실행
```bash
python main.py
```

## 사용법

### 관리자 기능

#### 과정 공개 설정
1. 관리자 포털 (`/admin`) 접속
2. "과정 관리" 섹션에서 과정의 공개 여부 토글
3. 공개로 설정된 과정은 로그인 없이 접근 가능

#### 랩 공개 설정
1. 랩 관리 페이지 (`/admin/lab`) 접속
2. 랩 추가/수정 시 "공개 여부" 선택
3. 공개 랩은 로그인 없이 콘텐츠 확인 가능

#### 콘텐츠 공개 설정
1. 랩 콘텐츠 관리 페이지 (`/admin/lab_content`) 접속
2. 콘텐츠별로 공개 여부 설정
3. 공개 콘텐츠는 로그인 없이 학습 가능

### 사용자 기능

#### 공개 과정 접근
1. 메인 페이지에서 "🔓 공개 과정" 카드 클릭
2. 로그인 없이 바로 학습 시작
3. 모든 콘텐츠를 자유롭게 이용

#### 일반 과정 접근
1. 메인 페이지에서 일반 과정 카드 클릭
2. 회원가입 또는 로그인
3. 학습 진행 상황 추적 및 기록

## 공개 과정 설정 예시

### 과정을 공개로 설정
```sql
UPDATE training SET is_public = 1 WHERE training_key = '20250101';
```

### 특정 랩을 공개로 설정
```sql
UPDATE training_lab SET is_public = 1 WHERE training_key = '20250101' AND lab_id = 1;
```

### 특정 콘텐츠를 공개로 설정
```sql
UPDATE training_lab_contents SET is_public = 1 WHERE training_key = '20250101' AND lab_id = 1 AND content_id = 1;
```

## 보안 고려사항

- 공개 과정은 로그인 없이 접근 가능하므로 민감한 정보 포함 금지
- 공개 콘텐츠는 학습 목적의 일반적인 내용으로 제한
- 관리자 권한으로만 공개/비공개 설정 변경 가능

## 기술 스택

- **Backend**: FastAPI (Python)
- **Database**: MySQL
- **Frontend**: HTML, CSS, JavaScript
- **Markdown**: Marked.js 라이브러리
- **UI Framework**: 커스텀 CSS (다크 테마)

## 라이선스

이 프로젝트는 내부 사용을 위한 교육 플랫폼입니다.
