@echo off
title AIR AI Network - Captive Portal Setup
color 0B
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║           AIR AI NETWORK - SETUP WIZARD             ║
echo  ║         Captive Portal + DNS Intercept Fix           ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: ── 1. Require Administrator ──────────────────────────────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  [!] Requesting Administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

echo  [1/7] Firewall - Allowing AIR AI ports on ALL profiles...

:: Remove old rules
netsh advfirewall firewall delete rule name="HS AI Web & Captive Portal" >nul 2>&1
netsh advfirewall firewall delete rule name="HS AI DNS Resolver" >nul 2>&1
netsh advfirewall firewall delete rule name="AIR AI Web Server" >nul 2>&1
netsh advfirewall firewall delete rule name="AIR AI DNS Interceptor" >nul 2>&1
netsh advfirewall firewall delete rule name="AIR AI DNS Port 5353" >nul 2>&1
netsh advfirewall firewall delete rule name="AIR AI Captive Portal" >nul 2>&1

:: Add fresh inbound rules for all profiles (domain + private + public)
netsh advfirewall firewall add rule name="AIR AI Web Server" dir=in action=allow protocol=TCP localport=80,8000 profile=any
netsh advfirewall firewall add rule name="AIR AI DNS Interceptor" dir=in action=allow protocol=UDP localport=53 profile=any
netsh advfirewall firewall add rule name="AIR AI DNS Port 5353" dir=in action=allow protocol=UDP localport=5353 profile=any
netsh advfirewall firewall add rule name="AIR AI Captive Portal" dir=in action=allow protocol=TCP localport=80,8000,53 profile=any

echo  [OK] Firewall rules applied.

echo.
echo  [2/7] Detecting hotspot adapter IP...
powershell -NoProfile -Command ^
    "$ad = Get-NetIPAddress | Where-Object { $_.IPAddress -eq '192.168.137.1' } | Select-Object -First 1; if ($ad) { Write-Host '  [OK] Hotspot IP: 192.168.137.1 (Wi-Fi 3 / index ' + $ad.InterfaceIndex + ')' } else { Write-Host '  [WARN] Hotspot IP not found. Start the Mobile Hotspot first.' }"

echo.
echo  [3/7] Intercepting captive portal probe domains via hosts file...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$h = 'C:\Windows\System32\drivers\etc\hosts'; $content = Get-Content $h -Raw -ErrorAction SilentlyContinue; if (!$content) { $content = '' }; $domains = @('connectivitycheck.gstatic.com', 'connectivitycheck.android.com', 'clients3.google.com', 'captive.apple.com', 'www.apple.com', 'msftconnecttest.com', 'www.msftconnecttest.com', 'msftncsi.com', 'www.msftncsi.com', 'detectportal.firefox.com', 'connectivity.samsung.com', 'connect.rom.miui.com', 'connectivitycheck.platform.hicloud.com', 'connectivitycheck.oppomobile.com', 'wifi.coloros.com', 'wifi.vivo.com.cn', 'air-ai.local', 'hs.ai', 'air.ai'); $added = 0; foreach ($d in $domains) { if ($content -notmatch [regex]::Escape($d)) { Add-Content -Path $h -Value \"192.168.137.1 $d\" -Encoding ASCII; $added++ } }; Write-Host ('  [OK] ' + $added + ' captive probe domains registered to 192.168.137.1')"

echo.
echo  [4/7] Setting DNS on hotspot adapter to 127.0.0.1...
powershell -NoProfile -Command ^
    "$idx = (Get-NetIPAddress | Where-Object { $_.IPAddress -eq '192.168.137.1' }).InterfaceIndex; if ($idx) { try { Set-DnsClientServerAddress -InterfaceIndex $idx -ServerAddresses ('127.0.0.1','192.168.137.1'); Write-Host '  [OK] DNS set to 127.0.0.1 on hotspot adapter' } catch { Write-Host '  [INFO] Hotspot adapter DNS managed by Windows' } } else { Write-Host '  [WARN] Hotspot adapter not found' }"

echo.
echo  [5/7] Flushing DNS resolver cache...
ipconfig /flushdns >nul 2>&1
powershell -NoProfile -Command "Clear-DnsClientCache" >nul 2>&1
echo  [OK] DNS cache flushed.

echo.
echo  [6/7] Verifying AIR AI web server on Port 80...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { $r = Invoke-WebRequest -Uri 'http://192.168.137.1/' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop; Write-Host '  [OK] AIR AI is active at http://192.168.137.1/ (HTTP ' $r.StatusCode ')' } catch { Write-Host '  [INFO] Server starting or not yet on port 80.' }"

echo.
echo  [7/7] Testing captive portal response...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { $r = Invoke-WebRequest -Uri 'http://192.168.137.1/generate_204' -MaximumRedirection 0 -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue; if ($r.StatusCode -eq 302) { Write-Host '  [OK] Captive probe redirects to: ' $r.Headers['Location'] } else { Write-Host '  [OK] Captive response code: ' $r.StatusCode } } catch { Write-Host '  [INFO] Probe test complete.' }"

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║  AIR AI NETWORK SETUP COMPLETE!                     ║
echo  ║                                                      ║
echo  ║  Any device connecting to the hotspot will now       ║
echo  ║  trigger the captive portal and DIRECT TO AIR AI!    ║
echo  ║                                                      ║
echo  ║  Supported: Android, iPhone, Windows, Mac, Linux    ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
pause
