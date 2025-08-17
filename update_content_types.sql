-- 기존 콘텐츠 타입을 10에서 1로 변경하는 SQL 스크립트
-- 실행 전에 데이터베이스 백업을 권장합니다.

-- training_lab_contents 테이블에서 lab_content_type이 10인 모든 레코드를 1로 변경
UPDATE training_lab_contents 
SET lab_content_type = 1 
WHERE lab_content_type = 10;

-- 변경된 레코드 수 확인
SELECT COUNT(*) as updated_records 
FROM training_lab_contents 
WHERE lab_content_type = 1;

-- 전체 콘텐츠 타입 분포 확인
SELECT lab_content_type, COUNT(*) as count 
FROM training_lab_contents 
GROUP BY lab_content_type 
ORDER BY lab_content_type;
