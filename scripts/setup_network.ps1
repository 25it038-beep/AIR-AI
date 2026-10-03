# ================================================================
# AIR AI NETWORK - AUTOMATED CAPTIVE PORTAL & FIREWALL CONFIGURATOR
# ================================================================
# Configures Windows Firewall for all network profiles (including Hotspot)
# and registers captive portal probe domains in the Windows hosts file.
# ================================================================

$ErrorActionPreference = "SilentlyContinue"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   AIR AI NETWORK - CAPTIVE PORTAL HARDENING SETUP        " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Windows Firewall Configuration
Write-Host "[1/4] Applying Windows Firewall rules for AIR AI..." -ForegroundColor Yellow

$rules = @(
    "AIR AI Web Server",
    "AIR AI Web Server 8000",
    "AIR AI Captive Portal 80",
    "AIR AI DNS Resolver",
    "AIR AI DNS Port 5353",
    "HS AI Web & Captive Portal",
    "HS AI DNS Resolver"
)

foreach ($r in $rules) {
    netsh advfirewall firewall delete rule name="$r" >$null 2>&1
}

# Allow TCP 80 and 8000 on ALL profiles (Public, Private, Domain)
netsh advfirewall firewall add rule name="AIR AI Web Server" dir=in action=allow protocol=TCP localport=80,8000 profile=any >$null 2>&1
netsh advfirewall firewall add rule name="AIR AI DNS Resolver" dir=in action=allow protocol=UDP localport=53,5353 profile=any >$null 2>&1

Write-Host "  [OK] Inbound Firewall rules active on all profiles (TCP 80/8000, UDP 53/5353)" -ForegroundColor Green

# 2. Hosts File Registration
Write-Host "[2/4] Registering Captive Portal Probe Domains..." -ForegroundColor Yellow

$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$hotspotIp = "192.168.137.1"

$domains = @(
    # Android / Google
    "connectivitycheck.gstatic.com",
    "connectivitycheck.android.com",
    "clients3.google.com",
    "play.googleapis.com",
    "www.google.com",
    "google.com",
    # Apple iOS / macOS CNA
    "captive.apple.com",
    "www.apple.com",
    "apple.com",
    "www.airport.us",
    "www.ibook.info",
    "www.itools.info",
    "www.thinkdifferent.us",
    # Windows NCSI
    "msftconnecttest.com",
    "www.msftconnecttest.com",
    "msftncsi.com",
    "www.msftncsi.com",
    "ipv6.msftncsi.com",
    # Firefox / Linux
    "detectportal.firefox.com",
    # Samsung
    "connectivity.samsung.com",
    # Xiaomi / MIUI
    "connect.rom.miui.com",
    # Realme / Oppo / OnePlus (ColorOS / AllawnOS)
    "conn-service-in-04.allawnos.com",
    "allawnos.com",
    "wifi.coloros.com",
    "connectivitycheck.oppomobile.com",
    # Local Discovery
    "air-ai.local",
    "air.ai",
    "hs-ai.local",
    "hs.ai"
)

try {
    $existing = Get-Content $hostsPath -Raw -ErrorAction SilentlyContinue
    if (-not $existing) { $existing = "" }

    $linesToAdd = @()
    foreach ($d in $domains) {
        if ($existing -notmatch [regex]::Escape($d)) {
            $linesToAdd += "$hotspotIp $d"
        }
    }

    if ($linesToAdd.Count -gt 0) {
        Add-Content -Path $hostsPath -Value $linesToAdd -Encoding ASCII
        Write-Host "  [OK] Added $($linesToAdd.Count) captive probe domains pointing to $hotspotIp" -ForegroundColor Green
    } else {
        Write-Host "  [OK] Captive probe domains already registered" -ForegroundColor Green
    }
} catch {
    Write-Host "  [WARN] Could not update hosts file directly: $($_.Exception.Message)" -ForegroundColor Red
}

# 3. Hotspot Adapter DNS Setting
Write-Host "[3/4] Configuring Hotspot adapter DNS..." -ForegroundColor Yellow
try {
    $ad = Get-NetIPAddress | Where-Object { $_.IPAddress -eq $hotspotIp } | Select-Object -First 1
    if ($ad -and $ad.InterfaceIndex) {
        Set-DnsClientServerAddress -InterfaceIndex $ad.InterfaceIndex -ServerAddresses @("127.0.0.1", $hotspotIp) -ErrorAction SilentlyContinue
        Write-Host "  [OK] Hotspot adapter DNS set to 127.0.0.1" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] Hotspot adapter not currently active; will be intercepted via hosts" -ForegroundColor DarkGray
    }
} catch {
    Write-Host "  [INFO] Adapter DNS managed by Windows" -ForegroundColor DarkGray
}

# 4. Flush DNS Cache
Write-Host "[4/4] Flushing DNS cache..." -ForegroundColor Yellow
ipconfig /flushdns >$null 2>&1
Clear-DnsClientCache >$null 2>&1
Write-Host "  [OK] Windows DNS resolver cache cleared" -ForegroundColor Green

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   AIR AI CAPTIVE PORTAL HARDENING COMPLETE!              " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
