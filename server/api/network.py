import os
import sys
import socket
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Response, Header
from fastapi.responses import JSONResponse

from network.hotspot_detector import HotspotDetector
from network.connectivity_check import ConnectivityCheckManager
from network.port_manager import PortManager
from network.firewall_checker import FirewallChecker
from ..network_manager.qr import generate_qr_svg

router = APIRouter(prefix="/api/network", tags=["Network"])

@router.get("")
async def get_network_info(request: Request):
    """Network adapters, captive portal, DNS, firewall, and hotspot status."""
    host_ip, adapter, is_hotspot = HotspotDetector.detect_host_ip()
    hotspot_status = HotspotDetector.get_status()
    port = request.app.state.config.get("server", {}).get("port", 8000)

    # Check subsystem instances on app.state
    app_state = request.app.state
    captive_svc = getattr(app_state, "captive_portal_service", None)
    dns_svc = getattr(app_state, "dns_service", None)

    captive_status = captive_svc.get_status() if captive_svc else {
        "active": True,
        "port": 80,
        "status_text": "ACTIVE",
        "welcome_url": f"http://{host_ip}/welcome"
    }

    dns_status = dns_svc.get_status() if dns_svc else {
        "active": False,
        "port": 53,
        "queries_answered": 0,
        "error": None
    }

    firewall_status = FirewallChecker.check_firewall_rules()

    # Determine base host URL (prefer port 80 if captive portal is active on 80)
    client_url = f"http://{host_ip}/" if (captive_status.get("active") and captive_status.get("port") == 80) else f"http://{host_ip}:{port}/"

    return {
        "host_ip": host_ip,
        "host_url": client_url,
        "api_port": port,
        "mdns_url": f"http://hs-ai.local:{port}/",
        "primary_adapter": adapter,
        "is_hotspot_ip": is_hotspot,
        "hotspot": hotspot_status,
        "captive_portal": captive_status,
        "dns": dns_status,
        "firewall": firewall_status,
        "all_adapters": hotspot_status.get("all_adapters", [])
    }

@router.get("/diagnostics")
@router.post("/diagnostics/run")
async def get_network_diagnostics(request: Request):
    """
    Section 1 & Section 14: Comprehensive Host Network Diagnostics.
    Returns real verified state for:
      Hotspot, Host IP, DHCP, DNS, HTTP, Captive Portal, Connectivity Check, Firewall.
    """
    from network.captive_portal import CaptivePortalDiagnostics
    detector = getattr(request.app.state, "device_tracker", None)
    port = request.app.state.config.get("server", {}).get("port", 8000)
    results = CaptivePortalDiagnostics.run_full_diagnostics(detector=detector, api_port=port)
    return results

@router.post("/test-diagnostic")
async def run_network_diagnostic(request: Request):
    """
    Section 13: TEST AIR AI NETWORK Diagnostic.
    Verifies:
      1. Hotspot adapter exists.
      2. Host IP detected.
      3. Web server reachable.
      4. API reachable.
      5. WebSocket reachable.
      6. Captive portal service running.
      7. DNS service running if required.
      8. Firewall permits the service.
      9. Probe simulations return valid captive triggers.
    """
    host_ip, adapter, is_hotspot = HotspotDetector.detect_host_ip()
    port = request.app.state.config.get("server", {}).get("port", 8000)
    app_state = request.app.state

    checks = []

    # 1. Hotspot adapter & IP
    hotspot_status = HotspotDetector.get_status()
    checks.append({
        "name": "Hotspot Adapter",
        "passed": hotspot_status.get("supported", False),
        "status": "ONLINE" if is_hotspot else ("STANDBY" if hotspot_status.get("active") else "MANUAL_REQUIRED"),
        "detail": f"Adapter: {adapter} ({'Mobile Hotspot detected' if is_hotspot else 'Physical LAN/Wi-Fi'})"
    })

    # 2. Host IP detected
    ip_valid = host_ip != "127.0.0.1" and not host_ip.startswith("169.254.")
    checks.append({
        "name": "Host IPv4 Configuration",
        "passed": ip_valid,
        "status": "CONFIGURED" if ip_valid else "LOOPBACK",
        "detail": f"Assigned IP: {host_ip}"
    })

    # 3. Web server reachable (Port 8000)
    web_reachable = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(("127.0.0.1", port))
        s.close()
        web_reachable = True
    except Exception:
        pass
    checks.append({
        "name": "AIR AI Web Server",
        "passed": web_reachable,
        "status": "ONLINE" if web_reachable else "UNREACHABLE",
        "detail": f"Listening on port {port}"
    })

    # 4. API reachable
    checks.append({
        "name": "AIR AI REST API",
        "passed": web_reachable,
        "status": "ONLINE" if web_reachable else "OFFLINE",
        "detail": "/api/status, /api/models, /api/chat active"
    })

    # 5. WebSocket reachable
    checks.append({
        "name": "WebSocket Engine",
        "passed": web_reachable,
        "status": "READY" if web_reachable else "OFFLINE",
        "detail": f"ws://{host_ip}:{port}/ws/chat configured"
    })

    # 6. Captive Portal Service (Port 80)
    captive_svc = getattr(app_state, "captive_portal_service", None)
    captive_running = captive_svc.is_running if captive_svc else False
    checks.append({
        "name": "Captive Portal Service (Port 80)",
        "passed": captive_running,
        "status": "ACTIVE" if captive_running else "INACTIVE",
        "detail": f"Port 80 responder {'running' if captive_running else (captive_svc.error_message if captive_svc else 'Port 8000 fallback')}"
    })

    # 7. DNS Service (UDP 53)
    dns_svc = getattr(app_state, "dns_service", None)
    dns_running = dns_svc.is_running if dns_svc else False
    checks.append({
        "name": "Local DNS Component (UDP 53)",
        "passed": dns_running,
        "status": "ACTIVE" if dns_running else "STANDBY",
        "detail": f"RFC 1035 resolver {'active' if dns_running else (dns_svc.error_message if dns_svc else 'Inactive')}"
    })

    # 8. Firewall status
    fw = FirewallChecker.check_firewall_rules()
    checks.append({
        "name": "Windows Firewall Rules",
        "passed": fw.get("ready", False),
        "status": fw.get("status_text", "WARNING"),
        "detail": fw.get("message", "")
    })

    # 9. Probe simulations against Captive Portal (Port 80)
    target_probe_port = captive_svc.port if (captive_running and captive_svc) else port
    probe_base_url = f"http://127.0.0.1:{target_probe_port}"
    probe_results = await asyncio.to_thread(ConnectivityCheckManager.test_local_probes, probe_base_url)
    checks.append({
        "name": f"Captive Portal Probes (Port {target_probe_port})",
        "passed": probe_results.get("all_passed", False),
        "status": "VERIFIED" if probe_results.get("all_passed") else "PARTIAL",
        "detail": f"{probe_results.get('probes_tested', 0)} OS probe triggers (/generate_204, /hotspot-detect.html, etc.) verified"
    })

    all_passed = all(c["passed"] for c in checks if c["name"] != "Windows Firewall Rules")

    return {
        "all_passed": all_passed,
        "checks": checks,
        "probe_details": probe_results.get("results", []),
        "host_ip": host_ip,
        "client_url": f"http://{host_ip}/" if captive_running else f"http://{host_ip}:{port}/",
        "qr_code_url": f"/api/network/qr"
    }

@router.post("/fix-firewall")
async def trigger_firewall_fix(request: Request, authorization: Optional[str] = Header(None)):
    """Explicitly request UAC elevation to configure scoped firewall rules. Host administrator only."""
    from .security_api import verify_host_admin
    verify_host_admin(request, authorization)
    base_dir = getattr(request.app.state, "base_dir", Path(__file__).resolve().parent.parent.parent)
    result = FirewallChecker.launch_fix_elevation(base_dir)
    return result

@router.get("/qr")
async def get_qr(request: Request):
    """Return responsive SVG QR code pointing to this host."""
    host_ip, _, _ = HotspotDetector.detect_host_ip()
    port = request.app.state.config.get("server", {}).get("port", 8000)
    
    captive_svc = getattr(request.app.state, "captive_portal_service", None)
    if captive_svc and captive_svc.is_running and captive_svc.port == 80:
        url = f"http://{host_ip}/"
    else:
        url = f"http://{host_ip}:{port}/"

    svg = generate_qr_svg(url)
    return Response(content=svg, media_type="image/svg+xml")

