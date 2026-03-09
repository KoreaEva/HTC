# 감독자(Supervisor) 기능 가이드

## 개요

이 시스템에는 관리자(Admin)와 감독자(Supervisor) 두 가지 권한 수준이 있습니다:

- **관리자(Admin)**: 모든 과정을 관리하고, 과정/랩/사용자/콘텐츠를 생성/수정/삭제할 수 있습니다
- **감독자(Supervisor)**: 지정된 특정 과정의 모니터링 및 조회 권한만 있습니다

## 감독자 권한

감독자는 다음을 할 수 있습니다:
- ✅ 랩 목록 조회
- ✅ 랩 콘텐츠 조회
- ✅ 사용자 목록 조회
- ✅ 실시간 모니터링
- ✅ 개별 사용자 삭제

감독자는 다음을 할 수 없습니다:
- ❌ 다른 과정 접근
- ❌ 과정 생성/수정/삭제
- ❌ 전체 사용자 삭제
- ❌ 관리자 대시보드 접근

## 감독자 추가 방법

### 1. API를 통한 감독자 추가

관리자는 다음 API를 사용하여 감독자를 추가할 수 있습니다:

```bash
POST /api/admin/supervisors
Content-Type: application/json

{
  "training_key": "123456",
  "supervisor_name": "홍길동"
}
```

예시 (curl):
```bash
curl -X POST http://localhost:8000/api/admin/supervisors \
  -H "Content-Type: application/json" \
  -d '{"training_key":"123456","supervisor_name":"홍길동"}'
```

### 2. Python 스크립트를 통한 추가

```python
import requests

url = "http://localhost:8000/api/admin/supervisors"
data = {
    "training_key": "123456",
    "supervisor_name": "홍길동"
}

response = requests.post(url, json=data)
print(response.json())
```

### 3. 데이터베이스 직접 삽입

```sql
INSERT INTO training_supervisors (training_key, supervisor_name, is_active) 
VALUES ('123456', '홍길동', 1);
```

## 감독자 로그인 방법

1. 관리자 로그인 페이지(`/admin`)로 이동합니다
2. **"감독자"** 탭을 클릭합니다
3. **과정 키**(training_key)와 **이름**(등록된 감독자 이름)을 입력합니다
4. **Login** 버튼을 클릭합니다

로그인 성공 시, 해당 과정의 랩 관리 페이지로 자동 이동됩니다.

## 감독자 관리 API

### 특정 과정의 감독자 목록 조회
```bash
GET /api/admin/supervisors/{training_key}
```

### 감독자 삭제
```bash
DELETE /api/admin/supervisors/{supervisor_id}
```

## 보안 참고사항

- 감독자는 과정 키와 이름만으로 로그인할 수 있으므로, 이 정보를 안전하게 관리해야 합니다
- 각 감독자는 자신이 할당된 과정만 접근할 수 있습니다
- 다른 과정에 접근하려고 하면 접근이 거부되고 로그인 페이지로 리다이렉트됩니다

## 문제 해결

### "감독자 권한이 없습니다" 오류
- 관리자에게 문의하여 해당 과정에 대한 감독자 권한이 있는지 확인하세요
- 입력한 과정 키와 이름이 정확한지 확인하세요

### "접근 권한이 없습니다" 오류
- 다른 과정의 URL에 접근하려고 할 때 발생합니다
- 자신에게 할당된 과정만 접근할 수 있습니다

## 예시 시나리오

### 시나리오: "AI 기초 과정"의 감독자 추가

1. 관리자가 "AI 기초 과정"을 생성하고 과정 키가 "202401"이라고 가정
2. 관리자가 "김강사" 님을 이 과정의 감독자로 추가:
   ```bash
   curl -X POST http://localhost:8000/api/admin/supervisors \
     -H "Content-Type: application/json" \
     -d '{"training_key":"202401","supervisor_name":"김강사"}'
   ```
3. "김강사" 님이 로그인:
   - `/admin` 페이지로 이동
   - "감독자" 탭 클릭
   - 과정 키: `202401`
   - 이름: `김강사`
   - Login 클릭
4. 로그인 성공 후 "AI 기초 과정"의 랩 관리 페이지에서 학습자 모니터링 가능

## 추가 개선 사항

향후 다음 기능들을 추가할 수 있습니다:
- 관리자 UI에서 감독자 관리 기능
- 감독자별 세부 권한 설정
- 감독자 활동 로그
- 감독자 비밀번호 인증 추가
