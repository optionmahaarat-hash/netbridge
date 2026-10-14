@echo off
cd /d %~dp0
python main_lite.py
if errorlevel 1 pause
