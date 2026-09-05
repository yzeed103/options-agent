@echo off
setlocal
title Disable automatic backup

rem --- self-elevate to Administrator -------------------------------------
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

set "DRIVE=D:"
if not "%~1"=="" set "DRIVE=%~1"

echo.
echo ==================================================================
echo   STEP 1 of 2 - scanning %DRIVE% . Nothing is changed yet.
echo ==================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0disable_auto_backup.ps1" -Drive %DRIVE%

echo.
echo ==================================================================
echo   STEP 2 of 2
echo ==================================================================
echo.
echo   Y = disable everything listed above (this is what you want)
echo   N = quit and change nothing
echo.
choice /c YN /n /m "Disable all of it now? [Y/N] "

if errorlevel 2 (
    echo.
    echo Nothing was changed. You can close this window.
    pause
    exit /b
)

echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0disable_auto_backup.ps1" -Drive %DRIVE% -Apply -IncludeThirdParty

echo.
echo ==================================================================
echo   Finished. Please restart the computer, then run this file again
echo   to confirm that everything now reports CLEAN.
echo ==================================================================
echo.
pause
