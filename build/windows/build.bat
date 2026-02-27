@echo off
REM Build script for QLayout Windows EXE

setlocal enabledelayedexpansion

echo.
echo 🔨 Building QLayout for Windows...
echo.

REM Check if PyInstaller is installed
where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo ❌ PyInstaller not found. Install with: pip install pyinstaller
    exit /b 1
)

REM Check if icon exists
if not exist "build\windows\qlayout.ico" (
    echo ⚠️  Icon not found at build\windows\qlayout.ico
    echo    Using default icon for now. You can create one with ImageMagick:
    echo    convert icon.png qlayout.ico
    echo.
)

REM Clean previous builds
echo 🧹 Cleaning previous builds...
if exist "build\__pycache__" rmdir /s /q build\__pycache__ 2>nul
if exist "dist" rmdir /s /q dist 2>nul
if exist "build\windows\qlayout" rmdir /s /q build\windows\qlayout 2>nul

REM Create PyInstaller spec for Windows
echo 📝 Creating PyInstaller spec for Windows...

REM Run PyInstaller with basic options
echo 📦 Running PyInstaller...
pyinstaller --onefile ^
    --windowed ^
    --name=qlayout ^
    --distpath=build\windows ^
    --workpath=build\__pycache__ ^
    --icon=build\windows\qlayout.ico ^
    --hidden-import=cewe_layout ^
    --hidden-import=cewe_layout.mcf_io ^
    --hidden-import=cewe_layout.algorithms ^
    --hidden-import=cewe_layout.utils ^
    --hidden-import=cewe_layout.book ^
    run_qlayout.py

if exist "build\windows\qlayout.exe" (
    echo.
    echo ✅ Build successful!
    echo.
    echo 📍 Output: build\windows\qlayout.exe
    echo.
    echo Next steps:
    echo   1. Test: build\windows\qlayout.exe
    echo   2. Create installer: Use InnoSetup or NSIS
) else (
    echo.
    echo ❌ Build failed. Check output above for errors.
    exit /b 1
)
