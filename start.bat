@echo off
echo Starting Data Analytics Agent...
echo.

cd backend

echo Installing dependencies with UV...
call uv pip install -r requirements.txt 2>nul
if %errorlevel% neq 0 (
    echo Installing dependencies...
    call uv pip sync
)

echo.
echo Creating sample database if needed...
python create_sample_db.py

echo.
echo Starting FastAPI server...
echo Server will be available at http://localhost:8080
echo.

uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080