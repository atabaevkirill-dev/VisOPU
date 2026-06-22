@echo off
REM ─────────────────────────────────────────────────────────────────────
REM  VisOPU Build Script — builds VisOPU.exe using PyInstaller
REM ─────────────────────────────────────────────────────────────────────
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo [1/3] Checking Python environment...
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Make sure python is in PATH.
    pause
    exit /b 1
)

echo.
echo [2/3] Installing/upgrading PyInstaller...
pip install pyinstaller --upgrade -q
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo [3/3] Building VisOPU.exe (this may take several minutes)...
pyinstaller VisOPU.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: Build failed! Check the output above for errors.
    pause
    exit /b 1
)

echo.
echo ═══════════════════════════════════════════════════════════
echo  BUILD SUCCESSFUL!
echo  Output: dist\VisOPU\VisOPU.exe
echo ═══════════════════════════════════════════════════════════
echo.
pause
