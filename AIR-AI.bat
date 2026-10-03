@echo off
title AIR AI Network - Local AI Appliance
color 0B

:: ========================================================
::          AIR AI NETWORK - ONE-CLICK LAUNCHER
:: ========================================================

set "APP_ROOT=%~dp0"
cd /d "%APP_ROOT%"

:: Check for Administrative Privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo  ======================================================
    echo    Requesting Administrator privileges for Network Setup
    echo  ======================================================
    echo.
    echo  AIR AI needs admin rights to:
    echo    1. Allow mobile devices through Windows Firewall (Port 80/8000)
    echo    2. Enable Captive Portal automatic popup on phones
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/c `\"%~f0`\"' -Verb RunAs"
    exit /b
)

echo.
echo  [1/2] Configuring Network & Captive Portal Interception...
if exist "%APP_ROOT%scripts\setup_network.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_ROOT%scripts\setup_network.ps1"
) else (
    netsh advfirewall firewall add rule name="AIR AI Web Server" dir=in action=allow protocol=TCP localport=80,8000 profile=any >nul 2>&1
    netsh advfirewall firewall add rule name="AIR AI DNS Resolver" dir=in action=allow protocol=UDP localport=53,5353 profile=any >nul 2>&1
    ipconfig /flushdns >nul 2>&1
)

echo.
echo  [2/2] Starting AIR AI Appliance Server...
:: Clean up any stale instances occupying ports 80 and 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :80\> ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000\> ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

:: Sync updated standalone executable from dist if available
if exist "%APP_ROOT%dist\HS-AI.exe" (
    copy /y "%APP_ROOT%dist\HS-AI.exe" "%APP_ROOT%AIR-AI.exe" >nul 2>&1
    copy /y "%APP_ROOT%dist\HS-AI.exe" "%APP_ROOT%HS-AI.exe" >nul 2>&1
)

:: Launch standalone executable if present
if exist "%APP_ROOT%HS-AI.exe" (
    "%APP_ROOT%HS-AI.exe" %*
    goto :AfterRun
)
if exist "%APP_ROOT%AIR-AI.exe" (
    "%APP_ROOT%AIR-AI.exe" %*
    goto :AfterRun
)

:: Detect Python
set "PYTHON_CMD="
if exist "%APP_ROOT%Shared\python\python.exe" (
    set "PYTHON_CMD=%APP_ROOT%Shared\python\python.exe"
    goto :Launch
)
python --version >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
    goto :Launch
)
py -3.12 --version >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3.12"
    goto :Launch
)
py --version >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_CMD=py"
    goto :Launch
)

echo ERROR: Python not found on system or USB drive.
pause
exit /b 1

:Launch
%PYTHON_CMD% "%APP_ROOT%HS-AI.py" %*

:AfterRun
if %errorlevel% neq 0 (
    echo.
    echo AIR AI exited with code %errorlevel%.
    pause
)
