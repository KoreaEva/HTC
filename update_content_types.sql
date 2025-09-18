-- 공개 랩 과정을 위한 is_public 필드 추가
-- training 테이블에 is_public 필드 추가 (기본값: 0 - 비공개)
ALTER TABLE training ADD COLUMN is_public TINYINT(1) DEFAULT 0 COMMENT '공개 여부 (1: 공개, 0: 비공개)';

-- training_lab 테이블에 is_public 필드 추가 (기본값: 0 - 비공개)
ALTER TABLE training_lab ADD COLUMN is_public TINYINT(1) DEFAULT 0 COMMENT '공개 여부 (1: 공개, 0: 비공개)';

-- training_lab_contents 테이블에 is_public 필드 추가 (기본값: 0 - 비공개)
ALTER TABLE training_lab_contents ADD COLUMN is_public TINYINT(1) DEFAULT 0 COMMENT '공개 여부 (1: 공개, 0: 비공개)';

-- 기존 데이터는 모두 비공개로 설정
UPDATE training SET is_public = 0 WHERE is_public IS NULL;
UPDATE training_lab SET is_public = 0 WHERE is_public IS NULL;
UPDATE training_lab_contents SET is_public = 0 WHERE is_public IS NULL;

-- 공개 과정 예시 (선택적으로 사용)
-- UPDATE training SET is_public = 1 WHERE training_key = '20250101';
-- UPDATE training_lab SET is_public = 1 WHERE training_key = '20250101' AND lab_id = 1;
-- UPDATE training_lab_contents SET is_public = 1 WHERE training_key = '20250101' AND lab_id = 1;
