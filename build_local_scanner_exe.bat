@echo off
setlocal
cd /d "%~dp0"

python -m PyInstaller ^
  --noconfirm ^
  --onedir ^
  --name local_scanner ^
  local_scanner.py

echo.
echo Build finished. Expected output:
echo dist\local_scanner\local_scanner.exe
pause
