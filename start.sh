#!/bin/bash

# requirements.txt에서 모든 의존성 설치
pip install -r requirements.txt

# FastAPI 애플리케이션 실행
uvicorn main:app --host=0.0.0.0 --port=8000
