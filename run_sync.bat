@echo off
:: ============================================================================
:: run_sync.bat
:: Runs the finance sync pipeline.
::
:: Usage:
::   Double-click to run manually, or point Windows Task Scheduler here
::   for automated daily execution.
::
:: Task Scheduler settings:
::   Action:  Start a program
::   Program: Full path to this file
::            e.g. C:\Users\YourName\finance_sync\run_sync.bat
::   Start in: (leave blank — the cd command below handles it)
::
:: Output:
::   Logs are written to logs\sync.log on every run.
::   cash_flow.csv is written to data\ for Excel import.
:: ============================================================================

cd /d "%~dp0"

:: Activate virtual environment if it exists.
:: If no venv, falls through and uses the system Python — still works
:: as long as dependencies are installed globally.
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo.
echo ============================================================
echo  Finance Sync - Running Pipeline
echo  %DATE% %TIME%
echo ============================================================
echo.

python main.py

set SYNC_RESULT=%errorlevel%

echo.
if %SYNC_RESULT% equ 0 (
    echo ============================================================
    echo  Pipeline completed successfully.
    echo  Check data\cash_flow.csv and logs\sync.log for details.
    echo ============================================================
) else (
    echo ============================================================
    echo  Pipeline exited with errors (code %SYNC_RESULT%).
    echo  Check logs\sync.log for details.
    echo ============================================================
)
echo.

:: When run manually: pause so the window stays open for review.
:: When run via Task Scheduler: the window closes automatically
:: because Task Scheduler does not inherit an interactive console.
:: To force the window to stay open in Task Scheduler, wrap this
:: script in: cmd /k run_sync.bat
pause
exit /b %SYNC_RESULT%
