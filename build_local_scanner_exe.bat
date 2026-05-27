@echo off
setlocal
cd /d "%~dp0"

python -m PyInstaller ^
  --noconfirm ^
  --onedir ^
  --name local_scanner ^
  --collect-all streamlit ^
  --copy-metadata streamlit ^
  --collect-all numpy ^
  --collect-all pandas ^
  --collect-all pyarrow ^
  --collect-all yfinance ^
  --collect-all curl_cffi ^
  --collect-all twstock ^
  local_scanner.py

echo.
echo Build finished. Expected output:
echo dist\local_scanner\local_scanner.exe
pause
