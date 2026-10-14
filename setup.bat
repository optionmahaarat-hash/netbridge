@echo off
cd /d %~dp0
python -m pip install -r requirements.txt
python get_xray.py
pause
