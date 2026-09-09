@echo off
TITLE ANG Automotive - BMW ECU Diagnostic & Remote Tuning Platform
COLOR 0B

echo ===============================================================================
echo     ANG AUTOMOTIVE - BMW M-PERFORMANCE TELEMATICS & REMOTE ECU TUNING
echo       ISO 13400 DoIP / ISO 14229 UDS Platform for Bosch MEVD17, MSD80, MG1
echo ===============================================================================
echo.

:: 1. Check Python Installation
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        COLOR 0C
        echo [ERROR] Python is not installed or not in your Windows PATH!
        echo Please install Python 3.10 or newer from https://www.python.org/downloads/
        echo (Make sure to check "Add Python to PATH" during installation)
        echo.
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=py
    )
) else (
    set PYTHON_CMD=python
)

echo [1/4] Found Python interpreter: %PYTHON_CMD%
%PYTHON_CMD% --version

:: 2. Check and Create Virtual Environment
if not exist "venv\Scripts\activate.bat" (
    echo [2/4] Creating Python Virtual Environment (venv)...
    %PYTHON_CMD% -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        COLOR 0C
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
) else (
    echo [2/4] Virtual environment (venv) detected.
)

:: Activate Virtual Environment
call venv\Scripts\activate.bat

:: 3. Install / Verify Dependencies
echo [3/4] Checking and installing Python dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    COLOR 0C
    echo [ERROR] Failed to install requirements. Please check your internet connection.
    pause
    exit /b 1
)
echo Dependencies verified.

:: 4. Launch Application and Open Web Browser
echo [4/4] Starting BMW Diagnostic & ECU Tuning Engine on http://localhost:5000...
echo.
echo ===============================================================================
echo   Platform is running on:
echo     - Web Dashboard: http://localhost:5000 (Opening in browser...)
echo     - DoIP Gateway:  Port 13400 (TCP / UDP)
echo.
echo   Press CTRL+C in this window to stop the server.
echo ===============================================================================
echo.

:: Open Browser after 2 seconds
start "" timeout /t 2 /nobreak >nul & start http://localhost:5000

:: Run the Flask Application
python app.py

pause
