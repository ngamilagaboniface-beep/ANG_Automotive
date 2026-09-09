@echo off
TITLE ANG Automotive - Build Standalone Windows .EXE Executable
COLOR 0B

echo ===============================================================================
echo     ANG AUTOMOTIVE - BUILD STANDALONE WINDOWS EXECUTABLE (ANG_BMW_Tuner.exe)
echo ===============================================================================
echo.

:: Check Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        COLOR 0C
        echo [ERROR] Python 3.10+ is required.
        pause
        exit /b 1
    )
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)

:: Activate Virtual Environment if present
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

echo [1/3] Installing PyInstaller and Build Requirements...
python -m pip install --upgrade pip --quiet
python -m pip install pyinstaller pywebview -r requirements.txt --quiet

echo [2/3] Compiling ANG_BMW_Tuner.exe with PyInstaller...
echo       Bundling WebGL maps, UDS stack, DoIP engine, and encryption modules...
python -m PyInstaller --clean ANG_BMW_Tuner.spec

if %ERRORLEVEL% NEQ 0 (
    COLOR 0C
    echo [ERROR] PyInstaller compilation failed. Check logs above.
    pause
    exit /b 1
)

echo [3/3] Build complete!
echo.
echo ===============================================================================
echo   SUCCESS: Standalone executable created at:
echo            dist\ANG_BMW_Tuner.exe
echo.
echo   You can now copy dist\ANG_BMW_Tuner.exe anywhere or run it directly!
echo ===============================================================================
echo.

:: Open dist folder in Windows Explorer
explorer dist

pause
