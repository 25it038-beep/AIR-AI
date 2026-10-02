@echo off
title AIR AI Network - Restore Network Defaults
color 07
echo.
echo  ======================================================
echo          AIR AI NETWORK - RESTORE DEFAULTS
echo  ======================================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

echo [1/3] Removing captive portal domain entries from hosts file...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$h = 'C:\Windows\System32\drivers\etc\hosts'; $lines = Get-Content $h; $filtered = $lines | Where-Object { $_ -notmatch '192\.168\.137\.1\s+(connectivitycheck|clients3\.google|captive\.apple|msftconnect|msftncsi|detectportal|connectivity\.samsung|connect\.rom\.miui|air-ai|hs\.ai|air\.ai)' }; Set-Content -Path $h -Value $filtered -Encoding ASCII; Write-Host '  [OK] Hosts file cleaned.'"

echo.
echo [2/3] Resetting hotspot adapter DNS...
powershell -NoProfile -Command ^
    "$idx = (Get-NetIPAddress | Where-Object { $_.IPAddress -eq '192.168.137.1' }).InterfaceIndex; if ($idx) { Set-DnsClientServerAddress -InterfaceIndex $idx -ResetServerAddresses; Write-Host '  [OK] Hotspot adapter DNS reset.' }"

echo.
echo [3/3] Flushing DNS cache...
ipconfig /flushdns >nul 2>&1
echo  [OK] DNS cache flushed.

echo.
echo Network settings restored to Windows defaults.
pause
