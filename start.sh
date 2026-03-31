#!/bin/bash

# requirements.txt에서 모든 의존성 설치
/opt/homebrew/opt/python@3.11/bin/python3.11 -m pip install -r requirements.txt

# FastAPI 애플리케이션 실행
/opt/homebrew/opt/python@3.11/bin/python3.11 -m uvicorn main:app --host=0.0.0.0 --port=8000 --reload
