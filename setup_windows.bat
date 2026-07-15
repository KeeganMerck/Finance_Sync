@echo off
:: ============================================================================
:: setup_windows.bat
:: One-time environment setup for finance_sync.
:: Run this once after downloading or cloning the project.
:: ============================================================================

:: Change to the directory containing this script, regardless of where
:: it is called from (works with Task Scheduler and double-click).
cd /d "%~dp0"

echo.
echo ============================================================
echo  Finance Sync - Environment Setup
echo ============================================================
echo.

:: ── Check Python is available ──────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Install Python 3.10+ from https://python.org
    echo         Ensure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version
echo.

:: ── Create virtual environment ─────────────────────────────────────────────
if exist venv\ (
    echo [SKIP] Virtual environment already exists at .\venv\
) else (
    echo [....] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK]   Virtual environment created.
)
echo.

:: ── Activate and upgrade pip ───────────────────────────────────────────────
echo [....] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

echo [....] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [OK]   pip up to date.
echo.

:: ── Install dependencies ───────────────────────────────────────────────────
echo [....] Installing dependencies from requirements.txt...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Dependency install failed. Check requirements.txt.
    pause
    exit /b 1
)
echo [OK]   Dependencies installed.
echo.

:: ── Create required directories if missing ─────────────────────────────────
if not exist data\   mkdir data
if not exist rules\  mkdir rules
if not exist logs\   mkdir logs
if not exist tests\  mkdir tests
echo [OK]   Project directories verified.
echo.

:: ── Done ───────────────────────────────────────────────────────────────────
echo ============================================================
echo  Setup complete.
echo.
echo  Next steps:
echo    1. Run the test suite:    run_tests.bat
echo    2. Run the pipeline:      run_sync.bat
echo    3. Open cash_flow.csv in Excel to verify your workbook.
echo ============================================================
echo.
pause
