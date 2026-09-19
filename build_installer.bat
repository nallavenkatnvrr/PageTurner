@echo off
setlocal
REM Builds PageTurner and packages it as a Windows installer (like 7-Zip's):
REM   installer\Output\PageTurner-Setup-1.1.0.exe
cd /d "%~dp0"

echo.
echo [1/3] Installing Python packages...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :fail

echo.
echo [2/3] Building PageTurner.exe...
python -m PyInstaller --noconfirm --clean --windowed --name PageTurner ^
  --icon assets\logo.ico --add-data "assets;assets" ^
  --collect-all pyhanko --collect-all pyhanko_certvalidator --collect-submodules aiohttp ^
  --collect-data certifi ^
  --version-file installer\version_info.txt pageturner.py || goto :fail

echo.
echo [3/3] Creating the installer...
call :find_iscc
if not defined ISCC (
  echo Inno Setup is not installed yet - installing it with winget...
  winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
  call :find_iscc
)
if not defined ISCC (
  echo.
  echo Inno Setup could not be found. Install it from https://jrsoftware.org/isdl.php
  echo and then run build_installer.bat again.
  goto :fail
)
"%ISCC%" installer\PageTurner.iss || goto :fail

echo.
echo Done! Your installer is:
echo   %~dp0installer\Output\PageTurner-Setup-1.1.0.exe
start "" explorer "%~dp0installer\Output"
pause
exit /b 0

:find_iscc
set "ISCC="
for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 7\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
) do if exist %%P set "ISCC=%%~P"
exit /b 0

:fail
echo.
echo Build failed - see the messages above.
pause
exit /b 1
