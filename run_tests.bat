@echo off
:: ============================================================================
:: run_tests.bat
:: Runs the full unit and integration test suite.
:: All 6 test files, all test classes, verbose output.
:: ============================================================================

cd /d "%~dp0"

:: Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo.
echo ============================================================
echo  Finance Sync - Test Suite
echo ============================================================
echo.

:: Run all test files via unittest discover.
:: -s tests     : start discovery in the tests/ directory
:: -p test_*.py : match all files named test_*.py
:: -v           : verbose output (one line per test)
python -m unittest discover -s tests -p "test_*.py" -v

:: Capture the exit code so we can show a clear pass/fail summary
set TEST_RESULT=%errorlevel%

echo.
if %TEST_RESULT% equ 0 (
    echo ============================================================
    echo  RESULT: ALL TESTS PASSED
    echo ============================================================
) else (
    echo ============================================================
    echo  RESULT: ONE OR MORE TESTS FAILED
    echo  Review the output above for details.
    echo ============================================================
)
echo.

pause
exit /b %TEST_RESULT%
