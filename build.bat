@echo off
REM Builds a standalone Windows app: dist\PageTurner\PageTurner.exe
cd /d "%~dp0"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name PageTurner ^
  --icon assets\logo.ico --add-data "assets;assets" ^
  --collect-all pyhanko --collect-all pyhanko_certvalidator --collect-submodules aiohttp ^
  --collect-data certifi pageturner.py
echo.
echo Done. Your app is in: %~dp0dist\PageTurner\PageTurner.exe
pause
