@echo off
setlocal

cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_hava_sahasi.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Startup failed with exit code %EXIT_CODE%.
    echo Check the messages above, then press any key to close this window.
    pause >nul
)

exit /b %EXIT_CODE%
