# pip install "fastapi>=0.109.0"
# pip install "uvicorn[standard]>=0.29.0"
# pip install "python-multipart>=0.0.6"
# pip install "pydantic>=2.0.0"
# pip install "pyodbc>=4.0.0"
# pip install "sqlalchemy>=2.0.0"

pip install -r requirements.txt

uvicorn main:app --host=0.0.0.0 --port=8000
#python -m uvicorn main:app --host 0.0.0.0 --port 80