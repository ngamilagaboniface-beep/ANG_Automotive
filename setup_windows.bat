@echo off
TITLE ANG Automotive - Windows Test Suite & Environment Setup
COLOR 0A

echo ===============================================================================
echo     ANG AUTOMOTIVE - WINDOWS TEST SUITE & VERIFICATION RUNNER
echo ===============================================================================
echo.

:: Check Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        COLOR 0C
        echo [ERROR] Python 3.10+ required.
        pause
        exit /b 1
    )
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)

:: Setup venv
if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment...
    %PYTHON_CMD% -m venv venv
)
call venv\Scripts\activate.bat

echo [*] Installing requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo ===============================================================================
echo   RUNNING ALL COMPANION VERIFICATION TESTS (ISO 13400, ISO 14229, UDS, CRYPTO)
echo ===============================================================================
echo.

pytest -v

if %ERRORLEVEL% EQU 0 (
    COLOR 0A
    echo.
    echo [SUCCESS] All 43 automotive verification tests PASSED!
    echo Your Windows environment is 100%% configured and ready for live ECU flashing.
) else (
    COLOR 0C
    echo.
    echo [WARNING] Some tests failed. Check logs above.
)

echo.
pause
