import time
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse

from ..hotspot_detector import HotspotDetector

logger = logging.getLogger("hs_ai.captive_portal.endpoints")

router = APIRouter(tags=["Captive Portal & Connectivity Checks"])

# ── Helpers ──────────────────────────────────────────────────────

def get_host_ip(request: Optional[Request] = None) -> str:
    ip, _, _ = HotspotDetector.detect_host_ip()
    return ip

def get_portal_url(request: Optional[Request] = None) -> str:
    """http://<hotspot-ip>/ — always port 80 for captive portal compatibility."""
    return f"http://{get_host_ip(request)}/"

def get_destination_url(request: Optional[Request] = None) -> str:
    """
    Direct to AI Chat (/chat) if no PIN is required,
    or to Welcome Portal (/welcome) if PIN authentication is enforced.
    """
    host_ip = get_host_ip(request)
    port = request.url.port if request else 80
    port_suffix = f":{port}" if port and port not in (80, 8000) else ""

    require_pin = False
    if request and hasattr(request, "app") and hasattr(request.app, "state"):
        config = getattr(request.app.state, "config", {})
        require_pin = config.get("security", {}).get("require_pin", False)

    target_path = "/welcome" if require_pin else "/chat"
    return f"http://{host_ip}{port_suffix}{target_path}"

def get_welcome_url(request: Optional[Request] = None) -> str:
    return get_destination_url(request)

def _redirect_html(target: str, title: str = "AIR AI Network") -> str:
    """Instant meta-refresh + JS redirect page."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={target}">
  <title>{title}</title>
  <script>window.location.replace("{target}");</script>
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#090d16;color:#e2e8f0;text-align:center;padding:2rem;margin:0;">
  <p style="color:#2dd4bf;font-size:1.1rem;">Connecting to AIR AI...</p>
  <p><a href="{target}" style="color:#2dd4bf;font-weight:600;">Tap here if not redirected</a></p>
</body>
</html>"""

def _record_probe(request: Request, client_family: str, endpoint: str, status_code: int = 302):
    """Log captive portal probe hit."""
    try:
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
        ua = request.headers.get("user-agent", "")
        now_str = time.strftime("%H:%M:%S", time.localtime())
        logger.info(f"[{now_str}] CAPTIVE PROBE | {endpoint} | {client_family} | IP:{client_ip} | HTTP{status_code}")
        app_state = request.app.state
        if hasattr(app_state, "device_tracker"):
            dt = app_state.device_tracker
            if hasattr(dt, "record_captive_hit"):
                dt.record_captive_hit(ip=client_ip, endpoint=endpoint, user_agent=ua, status_code=status_code, client_family=client_family)
            else:
                dt.register_or_update(client_ip, ua)
    except Exception as e:
        logger.debug(f"Probe record error: {e}")

# ── CAPTIVE PORTAL RESPONSE LOGIC ────────────────────────────────
#
# HOW CAPTIVE PORTAL DETECTION WORKS (per OS):
#
#  ANDROID:  GET /generate_204 → expect HTTP 204 (no content) = real internet
#            If we return anything else (200 with body, or 302), Android shows
#            "Sign in to network" notification → user taps → browser opens.
#            BEST: Return HTTP 302 to /welcome. Android NetworkMonitor opens it.
#
#  APPLE:    GET /hotspot-detect.html → expect "<HTML><HEAD><TITLE>Success</TITLE>"
#            If page title is NOT "Success", Apple CNA shows captive login sheet.
#            BEST: Return 200 with wrong title → Apple opens CNA modal.
#
#  WINDOWS:  GET /connecttest.txt → expect body "Microsoft Connect Test"
#            GET /ncsi.txt        → expect body "Microsoft NCSI"
#            If body doesn't match exactly, Windows shows "Connected, no internet"
#            notification with "Additional sign-in required" → opens IE/Edge.
#            BEST: Return 200 with wrong body OR 302 to /welcome.
#
#  SAMSUNG:  GET /generate_204 + some Samsung-specific domains
#  REALME/OPPO: Same as Android (AOSP connectivity check)
#  ONEPLUS:  Same as Android
#  XIAOMI:   GET /generate_204 + /ptlogin/status
#
# ── 1. Android / AOSP / Realme / OnePlus / Samsung / Xiaomi ─────

@router.api_route("/generate_204", methods=["GET", "HEAD"])
@router.api_route("/generate204", methods=["GET", "HEAD"])
@router.api_route("/gen_204", methods=["GET", "HEAD"])
@router.api_route("/gen204", methods=["GET", "HEAD"])
@router.api_route("/check_network_status.txt", methods=["GET", "HEAD"])
async def android_captive_check(request: Request):
    """
    Android connectivity probe — returns HTTP 302 instead of 204.
    Android NetworkMonitor: HTTP 204 = real internet (no captive).
    HTTP 302 = captive portal detected → shows 'Sign in to network'.
    """
    target = get_welcome_url(request)
    _record_probe(request, "Android/AOSP", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={
            "Location": target,
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )

@router.api_route("/.well-known/captive-portal", methods=["GET", "HEAD"])
@router.api_route("/api/captive-portal", methods=["GET", "HEAD"])
async def rfc8908_captive_portal(request: Request):
    """
    RFC 8908 / RFC 8910 Captive-Portal API Endpoint.
    Natively queried by modern Android 11+ and iOS 14+ devices.
    """
    target = get_welcome_url(request)
    _record_probe(request, "RFC 8908 Client", "/.well-known/captive-portal", 200)
    return JSONResponse(
        content={
            "captive": True,
            "user-portal-url": target,
            "venue-info-url": target,
            "seconds-remaining": 86400,
            "can-extend-session": True
        }
    )

@router.api_route("/mobile/status.php", methods=["GET", "HEAD"])
@router.api_route("/wifi/status", methods=["GET", "HEAD"])
async def samsung_check(request: Request):
    """Samsung captive portal probe."""
    target = get_welcome_url(request)
    _record_probe(request, "Samsung", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

@router.api_route("/ptlogin/status", methods=["GET", "HEAD"])
@router.api_route("/connect.rom.miui.com", methods=["GET", "HEAD"])
async def xiaomi_check(request: Request):
    """Xiaomi / MIUI / HyperOS captive probe."""
    target = get_welcome_url(request)
    _record_probe(request, "Xiaomi/MIUI", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

@router.api_route("/hw/connectivity.html", methods=["GET", "HEAD"])
async def huawei_check(request: Request):
    """Huawei / HarmonyOS captive probe."""
    target = get_welcome_url(request)
    _record_probe(request, "Huawei/HarmonyOS", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

# ── 2. Apple iOS / iPadOS / macOS (CNA) ─────────────────────────

@router.api_route("/hotspot-detect.html", methods=["GET", "HEAD"])
@router.api_route("/hotspotdetect.html", methods=["GET", "HEAD"])
async def apple_cna_hotspot(request: Request):
    """
    Apple CNA primary probe.
    Returning HTTP 302 with Location causes Apple CNA to pop up the login sheet
    and navigate directly to the AIR AI interface.
    """
    target = get_welcome_url(request)
    _record_probe(request, "Apple iOS/macOS CNA", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={
            "Location": target,
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }
    )

@router.api_route("/library/test/success.html", methods=["GET", "HEAD"])
@router.api_route("/success.html", methods=["GET", "HEAD"])
async def apple_success(request: Request):
    """
    Apple secondary probe — /library/test/success.html should return 'Success'.
    Return 302 redirect so Apple CNA opens the captive portal page.
    """
    target = get_welcome_url(request)
    _record_probe(request, "Apple iOS/macOS", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

@router.api_route("/bag", methods=["GET", "HEAD"])
async def apple_bag(request: Request):
    """Apple /bag probe — redirect to portal."""
    target = get_welcome_url(request)
    _record_probe(request, "Apple iOS", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

# ── 3. Windows NCSI ──────────────────────────────────────────────

@router.api_route("/connecttest.txt", methods=["GET", "HEAD"])
@router.api_route("/msftconnecttest.txt", methods=["GET", "HEAD"])
async def windows_connect_test(request: Request):
    """
    Windows NCSI probe: expects EXACT response body 'Microsoft Connect Test'.
    Returning wrong body OR 302 triggers 'Sign-in required' notification.
    We return 302 → Windows shows sign-in notification → user clicks → browser opens portal.
    """
    target = get_welcome_url(request)
    _record_probe(request, "Windows NCSI", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={
            "Location": target,
            "Cache-Control": "no-cache, no-store, must-revalidate",
        }
    )

@router.api_route("/ncsi.txt", methods=["GET", "HEAD"])
async def windows_ncsi(request: Request):
    """
    Windows NCSI secondary check: expects 'Microsoft NCSI'.
    Return wrong content → Windows flags as limited connectivity → notification shown.
    """
    target = get_welcome_url(request)
    _record_probe(request, "Windows NCSI", "/ncsi.txt", 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

@router.api_route("/redirect", methods=["GET", "HEAD"])
async def windows_redirect(request: Request):
    """Windows redirect check."""
    target = get_welcome_url(request)
    _record_probe(request, "Windows", "/redirect", 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

# ── 4. Firefox / Linux ────────────────────────────────────────────

@router.api_route("/canonical.html", methods=["GET", "HEAD"])
@router.api_route("/check_network_status.txt", methods=["GET", "HEAD"])
@router.api_route("/check_network", methods=["GET", "HEAD"])
@router.api_route("/check.txt", methods=["GET", "HEAD"])
async def firefox_linux_check(request: Request):
    """Firefox/Linux captive portal probes."""
    target = get_welcome_url(request)
    _record_probe(request, "Firefox/Linux", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

# ── 5. Kindle / Amazon Fire OS ────────────────────────────────────

@router.api_route("/kindle-wifi/wifiredirect.html", methods=["GET", "HEAD"])
@router.api_route("/kindle-wifi", methods=["GET", "HEAD"])
async def kindle_check(request: Request):
    """Amazon Kindle / Fire OS captive probe."""
    target = get_welcome_url(request)
    _record_probe(request, "Kindle/FireOS", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

# ── 6. Network Auto-Discovery / Generic ──────────────────────────

@router.api_route("/wpad.dat", methods=["GET", "HEAD"])
@router.api_route("/wpad.da", methods=["GET", "HEAD"])
@router.api_route("/proxy.pac", methods=["GET", "HEAD"])
async def wpad_proxy(request: Request):
    """WPAD proxy auto-discovery — return empty PAC to prevent proxy loops."""
    return Response(
        content='function FindProxyForURL(url, host) { return "DIRECT"; }',
        media_type="application/x-ns-proxy-autoconfig",
        status_code=200
    )

@router.api_route("/login", methods=["GET", "HEAD"])
@router.api_route("/logon", methods=["GET", "HEAD"])
@router.api_route("/portal", methods=["GET", "HEAD"])
@router.api_route("/landing", methods=["GET", "HEAD"])
@router.api_route("/wifi", methods=["GET", "HEAD"])
@router.api_route("/index.html", methods=["GET", "HEAD"])
@router.api_route("/index.htm", methods=["GET", "HEAD"])
@router.api_route("/default.html", methods=["GET", "HEAD"])
@router.api_route("/default.htm", methods=["GET", "HEAD"])
@router.api_route("/success.txt", methods=["GET", "HEAD"])
async def generic_portal_redirect(request: Request):
    """Generic portal redirect — any browser navigating to these gets the portal."""
    target = get_welcome_url(request)
    _record_probe(request, "Generic Browser", request.url.path, 302)
    return Response(
        content=_redirect_html(target),
        status_code=302,
        media_type="text/html",
        headers={"Location": target, "Cache-Control": "no-cache, no-store, must-revalidate"}
    )

# Backward compatibility alias
generic_probe = generic_portal_redirect

# ── 7. Welcome Landing Page ───────────────────────────────────────

@router.api_route("/welcome", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def welcome_page(request: Request):
    """Root captive portal welcome page — serves portal.html."""
    _record_probe(request, "Browser", "/welcome", 200)
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    portal_file = frontend_dir / "portal.html"
    if portal_file.exists():
        return FileResponse(str(portal_file), media_type="text/html")
    return HTMLResponse("<h1>AIR AI Network</h1><p>Welcome Portal</p><a href='/chat'>Start Chat</a>")

@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def root_auto_direct(request: Request):
    """Direct root path straight to AI Chat if no PIN required, or to welcome page if PIN is active."""
    require_pin = False
    if hasattr(request, "app") and hasattr(request.app, "state"):
        config = getattr(request.app.state, "config", {})
        require_pin = config.get("security", {}).get("require_pin", False)
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    if not require_pin:
        chat_file = frontend_dir / "chat.html"
        if chat_file.exists():
            return FileResponse(str(chat_file), media_type="text/html")
        return HTMLResponse("<h1>AIR AI Chat</h1>")
    portal_file = frontend_dir / "portal.html"
    if portal_file.exists():
        return FileResponse(str(portal_file), media_type="text/html")
    return HTMLResponse("<h1>AIR AI Network</h1><p>Welcome Portal</p><a href='/chat'>Start Chat</a>")

# ── 8. Connectivity API ───────────────────────────────────────────

@router.get("/connectivity-check")
async def connectivity_check_api(request: Request):
    """JSON probe for testing captive portal health."""
    host_ip, adapter, is_hotspot = HotspotDetector.detect_host_ip()
    return JSONResponse({
        "status": "captive_portal_active",
        "host_ip": host_ip,
        "adapter": adapter,
        "is_hotspot": is_hotspot,
        "portal_url": get_portal_url(request),
        "welcome_url": get_welcome_url(request),
        "timestamp": time.time()
    })

@router.get("/health")
async def health(request: Request):
    """Simple health endpoint."""
    return JSONResponse({"status": "ok", "service": "AIR AI Network"})

# ── 9. Diagnostic Test Page ───────────────────────────────────────

@router.get("/test/captive-portal", response_class=HTMLResponse)
async def captive_portal_test_page(request: Request):
    """
    Human-readable captive portal diagnostic page.
    Open http://192.168.137.1/test/captive-portal on a connected device to verify.
    """
    host_ip, adapter, _ = HotspotDetector.detect_host_ip()
    ua = request.headers.get("user-agent", "")

    from .detector import ClientDetector
    parsed = ClientDetector.parse_user_agent(ua)
    client_label = f"{parsed['os_family']} ({parsed['os_version']})" if parsed.get('os_version', 'Unknown') != "Unknown" else parsed.get('os_family', 'Unknown')

    app_state = request.app.state
    dns_status = "● RUNNING"
    dns_color = "#34d399"
    if hasattr(app_state, "dns_service") and app_state.dns_service:
        dns_st = app_state.dns_service.get_status()
        if dns_st.get("fallback_mode"):
            dns_status = "⚠ Fallback Mode (Windows ICS)"
            dns_color = "#fbbf24"
        elif not dns_st.get("running"):
            dns_status = "✗ NOT RUNNING"
            dns_color = "#f87171"
        else:
            dns_status = f"● ACTIVE (ports: {dns_st.get('active_ports', [53])})"
            dns_color = "#34d399"

    welcome = get_welcome_url(request)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AIR AI - Captive Portal Diagnostics</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #090d16; color: #e2e8f0; margin: 0; padding: 1rem;
           display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; }}
    .card {{ background: #111827; border: 1px solid #1f2937; border-radius: 14px;
             padding: 1.5rem; max-width: 440px; width: 100%; margin-top: 1rem; }}
    h2 {{ color: #2dd4bf; margin: 0 0 1rem; font-size: 1.1rem; letter-spacing: .07em;
          text-transform: uppercase; border-bottom: 1px solid #1f2937; padding-bottom: .75rem; }}
    .row {{ display: flex; justify-content: space-between; align-items: center;
            padding: .55rem 0; border-bottom: 1px solid #162032; font-size: .92rem; }}
    .label {{ color: #94a3b8; }}
    .val {{ font-weight: 600; }}
    .ok {{ color: #34d399; }}
    .warn {{ color: #fbbf24; }}
    .btn {{ display: block; margin-top: 1.4rem; background: linear-gradient(135deg,#0d9488,#0284c7);
            color: #fff; text-decoration: none; text-align: center; padding: .8rem;
            border-radius: 9px; font-weight: 700; letter-spacing: .04em; font-size: 1rem; }}
    .note {{ font-size: .78rem; color: #64748b; margin-top: 1rem; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>AIR AI — Captive Portal Diagnostics</h2>
    <div class="row"><span class="label">Your Device</span><span class="val">{client_label}</span></div>
    <div class="row"><span class="label">AIR AI Host IP</span><span class="val ok">{host_ip}</span></div>
    <div class="row"><span class="label">Hotspot Adapter</span><span class="val">{adapter}</span></div>
    <div class="row"><span class="label">HTTP Server</span><span class="val ok">● ACTIVE (Port 80)</span></div>
    <div class="row"><span class="label">DNS Interceptor</span><span class="val" style="color:{dns_color};">{dns_status}</span></div>
    <div class="row"><span class="label">Captive Portal</span><span class="val ok">● REACHABLE</span></div>
    <div class="row"><span class="label">Portal URL</span><span class="val ok">{welcome}</span></div>
    <a href="{welcome}" class="btn">→ Enter AIR AI</a>
    <p class="note">
      If your phone did not auto-open this page when connecting to the hotspot,
      run <b>scripts/airai_network_setup.bat</b> as Administrator on the host laptop,
      then reconnect your phone. For best results, disconnect the laptop from home Wi-Fi.
    </p>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)
