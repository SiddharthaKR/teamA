@echo off
setlocal enableextensions
cd /d "C:\Study Materials\Hackathon\teamA"

set "LOG=run_app.log"
echo === SETUP START %date% %time% > "%LOG%" 2>&1

REM --- locate Python launcher ---
where py >nul 2>&1
if errorlevel 1 (
    echo PY_LAUNCHER_MISSING >> "%LOG%" 2>&1
    echo SETUP_FAIL >> "%LOG%" 2>&1
    goto :hold
)

REM --- create venv if missing ---
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment with Python 3.14... >> "%LOG%" 2>&1
    py -3.14 -m venv .venv >> "%LOG%" 2>&1
)

if not exist ".venv\Scripts\python.exe" (
    echo VENV_FAIL - Python 3.14 venv could not be created >> "%LOG%" 2>&1
    echo SETUP_FAIL >> "%LOG%" 2>&1
    goto :hold
)

echo Upgrading pip... >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m pip install --upgrade pip >> "%LOG%" 2>&1

echo Installing dependencies... >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt >> "%LOG%" 2>&1
if errorlevel 1 (
    echo PIP_FAIL >> "%LOG%" 2>&1
    echo SETUP_FAIL >> "%LOG%" 2>&1
    goto :hold
)

echo Running database migrations... >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m alembic upgrade head >> "%LOG%" 2>&1
if errorlevel 1 (
    echo ALEMBIC_FAIL >> "%LOG%" 2>&1
    echo SETUP_FAIL >> "%LOG%" 2>&1
    goto :hold
)

echo SETUP_OK >> "%LOG%" 2>&1
echo === STARTING STREAMLIT %date% %time% >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m streamlit run app.py >> "%LOG%" 2>&1

:hold
echo === SCRIPT ENDED %date% %time% >> "%LOG%" 2>&1
echo.
echo Finished. Review run_app.log for details. This window can be closed.
pause
