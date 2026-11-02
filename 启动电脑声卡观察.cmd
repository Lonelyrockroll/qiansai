@echo off
setlocal
pushd "%~dp0" || exit /b 1
python -B -X utf8 realtime_synth\host\audio_web.py --port 8768
if errorlevel 1 pause
popd
