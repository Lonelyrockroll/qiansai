@echo off
setlocal
pushd "%~dp0" || exit /b 1
python -B -X utf8 realtime_synth\host\server.py --port 8769 --latency-page
if errorlevel 1 pause
popd
