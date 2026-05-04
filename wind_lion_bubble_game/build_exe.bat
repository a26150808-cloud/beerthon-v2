@echo off
setlocal

cd /d "%~dp0"

echo.
echo ========================================
echo   Wind Lion Bubble Game - EXE Builder
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Please install Python 3.10 or newer.
    pause
    exit /b 1
)

echo Installing packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Package installation failed. Please check network and Python environment.
    pause
    exit /b 1
)

echo.
echo Building exe...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$n=[string]::Concat([char]0x98A8,[char]0x7345,[char]0x723A,[char]0x6233,[char]0x6CE1,[char]0x6CE1); python -m PyInstaller --noconfirm --clean --onefile --windowed --name $n main.py"
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Done.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$n=[string]::Concat([char]0x98A8,[char]0x7345,[char]0x723A,[char]0x6233,[char]0x6CE1,[char]0x6CE1); Write-Host ('EXE path: ' + (Join-Path (Join-Path (Get-Location) 'dist') ($n + '.exe')))"
echo.
pause
