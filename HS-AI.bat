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
echo  [1/4] Applying Windows Firewall rules for AIR AI...
netsh advfirewall firewall delete rule name="AIR AI Web Server" >nul 2>&1
netsh advfirewall firewall delete rule name="AIR AI DNS Resolver" >nul 2>&1
netsh advfirewall firewall delete rule name="HS AI Web & Captive Portal" >nul 2>&1
netsh advfirewall firewall delete rule name="HS AI DNS Resolver" >nul 2>&1

netsh advfirewall firewall add rule name="AIR AI Web Server" dir=in action=allow protocol=TCP localport=80,8000 profile=any >nul 2>&1
netsh advfirewall firewall add rule name="AIR AI DNS Resolver" dir=in action=allow protocol=UDP localport=53,5353 profile=any >nul 2>&1
echo        [OK] Firewall rules active (all profiles).

echo.
echo  [2/4] Enabling Captive Portal DNS Interception...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$h = 'C:\Windows\System32\drivers\etc\hosts'; $content = Get-Content $h -Raw -ErrorAction SilentlyContinue; if (!$content) { $content = '' }; $domains = @('connectivitycheck.gstatic.com', 'connectivitycheck.android.com', 'clients3.google.com', 'captive.apple.com', 'www.apple.com', 'msftconnecttest.com', 'www.msftconnecttest.com', 'msftncsi.com', 'www.msftncsi.com', 'detectportal.firefox.com', 'connectivity.samsung.com', 'connect.rom.miui.com', 'connectivitycheck.platform.hicloud.com', 'connectivitycheck.oppomobile.com', 'wifi.coloros.com', 'wifi.vivo.com.cn', 'air-ai.local', 'hs.ai', 'air.ai'); $added = 0; foreach ($d in $domains) { if ($content -notmatch [regex]::Escape($d)) { Add-Content -Path $h -Value \"192.168.137.1 $d\" -Encoding ASCII; $added++ } }; Write-Host ('       [OK] ' + $added + ' captive probe domains registered to 192.168.137.1')"

echo.
echo  [3/4] Flushing DNS cache...
ipconfig /flushdns >nul 2>&1
echo        [OK] DNS cache flushed.

echo.
echo  [4/4] Starting AIR AI Appliance Server...
echo.

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

if %errorlevel% neq 0 (
    echo.
    echo AIR AI exited with code %errorlevel%.
    pause
)
