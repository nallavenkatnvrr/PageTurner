@echo off
REM Runs PageTurner straight from source (installs dependencies the first time)
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
start "" pythonw pageturner.py %*
