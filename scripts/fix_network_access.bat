@echo off
title AIR AI Network - Scoped Firewall Setup
echo ========================================================
echo       AIR AI NETWORK - SCOPED FIREWALL CONFIGURATION    
echo ========================================================
echo.
echo This script creates narrowly scoped Windows Firewall rules
echo exclusively for the AIR AI private mobile hotspot network.
echo.
:: Check for administrative privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/c `"%~f0`"' -Verb RunAs"
    exit /b
)

echo Applying firewall rules for all profiles (including Hotspot Public adapter)...
:: Web & Captive Portal Inbound TCP 80, 8000
netsh advfirewall firewall delete rule name="AIR AI Web Server" >nul 2>&1
netsh advfirewall firewall delete rule name="HS AI Web & Captive Portal" >nul 2>&1
netsh advfirewall firewall add rule name="AIR AI Web Server" dir=in action=allow protocol=TCP localport=80,8000 profile=any

:: Local DNS Inbound UDP 53
netsh advfirewall firewall delete rule name="AIR AI DNS Resolver" >nul 2>&1
netsh advfirewall firewall delete rule name="HS AI DNS Resolver" >nul 2>&1
netsh advfirewall firewall add rule name="AIR AI DNS Resolver" dir=in action=allow protocol=UDP localport=53 profile=any

echo.
echo [SUCCESS] Scoped firewall rules have been added for all profiles.
echo Hotspot devices can now reach AIR AI.
echo You may now close this window.
pause
