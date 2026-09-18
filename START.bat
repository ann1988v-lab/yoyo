@echo off
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install -r requirements.txt
echo Starting SAKURA 18+...
python main.py
pause
