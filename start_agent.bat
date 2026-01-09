@echo off
cd /d %~dp0
REM Активируйте venv при необходимости: call venv\Scripts\activate
python agent_channel.py
pause
