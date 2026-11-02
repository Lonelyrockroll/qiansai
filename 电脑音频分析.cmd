@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist ".pc-analysis-env\Scripts\python.exe" (
    python -m venv --system-site-packages .pc-analysis-env || goto error
)
".pc-analysis-env\Scripts\python.exe" -c "import numpy,PIL" >nul 2>&1
if errorlevel 1 (
    ".pc-analysis-env\Scripts\python.exe" -m pip install -r tools\pc-analysis-requirements.txt || goto error
)
if "%~1"=="" (
    ".pc-analysis-env\Scripts\python.exe" -X utf8 tools\pc_audio_analysis.py example all32 --open
) else if /I "%~x1"==".pcm" (
    ".pc-analysis-env\Scripts\python.exe" -X utf8 tools\pc_audio_analysis.py file "%~f1" --open
) else (
    ".pc-analysis-env\Scripts\python.exe" -X utf8 tools\pc_audio_analysis.py %*
)
if errorlevel 1 goto error
popd
exit /b 0
:error
echo Analysis did not complete. See the message above.
popd
pause
exit /b 1
