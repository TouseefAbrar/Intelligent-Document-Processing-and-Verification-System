@echo off
setlocal
title EEF Project Launcher
cd /d "%~dp0"

echo ====================================================
echo   Ezitech Document Intelligence - Full Project Run
echo   Backend  : http://localhost:8000  (docs: /docs)
echo   Frontend : http://localhost:5173
echo ====================================================
echo.

REM ---- 1. Check Python is available ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH. Install Python 3.10+ first.
    pause
    exit /b 1
)

REM ---- 2. Backend venv + dependencies (first run only) ----
if not exist "backend\.venv\Scripts\python.exe" (
    echo [setup] Creating backend venv...
    python -m venv "backend\.venv"
    if errorlevel 1 (
        echo [ERROR] Failed to create the Python venv.
        pause
        exit /b 1
    )
    echo [setup] Installing backend requirements...
    "backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
    if errorlevel 1 (
        echo [ERROR] Failed to install backend requirements.
        pause
        exit /b 1
    )
)

REM ---- 3. Frontend dependencies (first run only) ----
if not exist "frontend\node_modules" (
    echo [setup] Installing frontend dependencies...
    pushd "frontend"
    call npm install
    popd
)

echo.
echo [start] Launching backend and frontend servers...
echo         Close the two new windows to stop the project.
echo.

REM ---- 4. Backend server window (FastAPI / uvicorn) ----
cd /d "%~dp0backend"
start "EEF Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

REM ---- 5. Frontend dev server window (Vite) ----
cd /d "%~dp0frontend"
start "EEF Frontend" cmd /k "npm run dev"

REM ---- 6. Open the browser once the servers have started ----
ping -n 5 127.0.0.1 >nul
start "" "http://localhost:5173"

cd /d "%~dp0"
echo.
echo [done] Frontend: http://localhost:5173
echo        Backend : http://localhost:8000  (API docs: /docs)
endlocal
