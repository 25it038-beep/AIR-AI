import os
import sys
import json
import time
import shutil
import asyncio
import webbrowser
import subprocess
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# Dynamic Base Path Resolution (No hardcoded paths)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure project directories exist
CONFIG_DIR = BASE_DIR / "config"
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
FRONTEND_DIR = BASE_DIR / "frontend"
SHARED_DIR = BASE_DIR / "Shared"

for d in (CONFIG_DIR, MODELS_DIR, DATA_DIR, LOGS_DIR, FRONTEND_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Imports from local modules
from launcher.hardware_detector import get_complete_hardware_profile, detect_usb_root
from launcher.model_scanner import select_best_model
from launcher.startup_banner import render_init_box, print_step, render_ready_summary

from server.logger_setup import setup_loggers
from server.model_manager.manager import ModelManager
from server.security import Firewall, RateLimiter, AuthManager
from server.network_manager import MDNSService

# Local Captive Portal Architecture Imports
from network import (
    HotspotDetector,
    CaptivePortalServer,
    DNSServer,
    ConnectivityCheckManager,
    DeviceDetector,
    PortManager,
    FirewallChecker,
    CaptiveHardener
)

from server.api import (
    captive_router,
    status_router,
    models_router,
    devices_router,
    network_router,
    chat_router,
    security_router,
    files_router
)
from server.websocket import ws_router

# Initialize Loggers
LOGGERS = setup_loggers(LOGS_DIR)
server_log = LOGGERS["server"]
model_log = LOGGERS["model"]
net_log = LOGGERS["network"]
sec_log = LOGGERS["security"]

# Load Configuration
config_file = CONFIG_DIR / "config.json"
default_config = {
    "app_name": "AIR AI Network",
    "server": {"host": "0.0.0.0", "port": 8000},
    "model": {"active_model": "llama3.2:latest", "max_concurrency": 3},
    "security": {"require_pin": False, "network_pin": "8888", "rate_limit_requests_per_min": 60, "max_connected_clients": 30}
}
if config_file.exists():
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = default_config
else:
    config = default_config
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

# Global Subsystem Instances
device_tracker = DeviceDetector(data_file=str(DATA_DIR / "devices.json"))
firewall = Firewall(max_clients=config.get("security", {}).get("max_connected_clients", 30))
rate_limiter = RateLimiter(requests_per_minute=config.get("security", {}).get("rate_limit_requests_per_min", 60))
auth_manager = AuthManager(
    require_pin=config.get("security", {}).get("require_pin", False),
    network_pin=config.get("security", {}).get("network_pin", "8888")
)
model_manager = ModelManager(models_root=str(MODELS_DIR), config=config)

# Ensure Engine Background Process (Ollama supervisor)
def ensure_local_engine():
    """Verify or launch local Ollama engine daemon."""
    server_log.info("Checking local AI inference engine supervisor...")
    import urllib.request
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1.0) as res:
            if res.status == 200:
                server_log.info("Local inference engine is already active.")
                return
    except Exception:
        pass

    # Look for ollama executable
    ollama_exe = None
    if shutil.which("ollama"):
        ollama_exe = "ollama"
    elif os.path.exists(r"C:\Users\BS.Harshan seliyan\AppData\Local\Programs\Ollama\ollama.exe"):
        ollama_exe = r"C:\Users\BS.Harshan seliyan\AppData\Local\Programs\Ollama\ollama.exe"
    elif (SHARED_DIR / "bin" / "ollama-windows.exe").exists():
        ollama_exe = str(SHARED_DIR / "bin" / "ollama-windows.exe")

    if ollama_exe:
        try:
            server_log.info(f"Starting local engine daemon via: {ollama_exe} serve")
            subprocess.Popen(
                [ollama_exe, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            time.sleep(1.5)
        except Exception as e:
            server_log.error(f"Failed to auto-spawn local engine: {e}")

# Create FastAPI Web Application
app = FastAPI(title="AIR AI Network", docs_url=None, redoc_url=None)

# Attach shared states
app.state.base_dir = BASE_DIR
app.state.model_manager = model_manager
app.state.device_tracker = device_tracker
app.state.firewall = firewall
app.state.rate_limiter = rate_limiter
app.state.auth_manager = auth_manager
app.state.config = config
app.state.chats_file = str(DATA_DIR / "chats.json")
app.state.settings_file = str(DATA_DIR / "settings.json")
app.state.captive_portal_service = None
app.state.dns_service = None

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Security & Tracking Middleware
class NetworkApplianceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
        ua = request.headers.get("user-agent", "")

        # 1. Firewall verification
        if firewall.is_blocked(client_ip):
            sec_log.warning(f"Blocked connection attempt from {client_ip}")
            return Response(content="Access blocked by AIR AI Host.", status_code=403)

        # 2. Device registration
        device_tracker.register_or_update(client_ip, ua)
        if client_ip not in ("127.0.0.1", "testclient"):
            print(f"  [INCOMING] {client_ip} -> {request.method} {request.url.path} (Host: {request.headers.get('host')})", flush=True)

        # 2.1 Strong Captive Portal Host Interception:
        # If incoming request is targeting an external internet domain (e.g. connectivitycheck.gstatic.com,
        # captive.apple.com, conn-service-in-04.allawnos.com, etc.),
        # intercept and redirect immediately to AIR AI Chat.
        host_header = request.headers.get("host", "").split(":")[0].lower()
        path = request.url.path
        host_ip, _, _ = HotspotDetector.detect_host_ip()
        exempt_hosts = {"127.0.0.1", "localhost", host_ip.lower(), "192.168.137.1", "hs.ai", "air.ai", "air-ai.local", "testserver"}
        if host_header and host_header not in exempt_hosts:
            if not path.startswith(("/static/", "/vendor/", "/api/", "/ws/", "/manifest.json", "/sw.js")):
                dest = f"http://{host_ip}/chat"
                return HTMLResponse(
                    content=f'<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0; url={dest}"><script>window.location.replace("{dest}");</script></head><body style="background:#090d16;color:#e2e8f0;text-align:center;padding:2rem;"><p>Connecting to AIR AI...</p><p><a href="{dest}" style="color:#2dd4bf;">Click here if not redirected</a></p></body></html>',
                    status_code=302,
                    headers={"Location": dest, "Cache-Control": "no-cache, no-store, must-revalidate"}
                )

        # 3. Rate Limiting for general API
        path = request.url.path
        if path.startswith("/api/"):
            bucket = "api"
            if path == "/api/auth/login":
                bucket = "auth"
            elif path.startswith("/api/chat"):
                bucket = "chat"
            elif path.startswith("/api/files/upload"):
                bucket = "file_upload"

            allowed, retry_after = rate_limiter.check_rate_limit(client_ip, bucket)
            if not allowed:
                sec_log.warning(f"Rate limit exceeded for {client_ip} on bucket {bucket}")
                return Response(
                    content=f"Too Many Requests. Please wait {retry_after} seconds.",
                    status_code=429,
                    headers={"Retry-After": str(retry_after)}
                )

        response = await call_next(request)

        # 4. HTTP Security Headers (Section 12)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: ws: wss:; frame-ancestors 'self';"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        return response

app.add_middleware(NetworkApplianceMiddleware)

# Mount Static Directories
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# Mount vendor assets from Shared if present (for fonts, highlight.js, marked)
vendor_dir = SHARED_DIR / "vendor"
if vendor_dir.exists():
    app.mount("/vendor", StaticFiles(directory=str(vendor_dir)), name="vendor")
elif (FRONTEND_DIR / "vendor").exists():
    app.mount("/vendor", StaticFiles(directory=str(FRONTEND_DIR / "vendor")), name="vendor")

# Include Routers
app.include_router(captive_router)
app.include_router(status_router)
app.include_router(models_router)
app.include_router(devices_router)
app.include_router(network_router)
app.include_router(chat_router)
app.include_router(security_router)
app.include_router(files_router)
app.include_router(ws_router)

# ── Progressive Web App (PWA) Endpoints ─────────────────────────
@app.get("/manifest.json")
async def get_manifest():
    manifest_file = FRONTEND_DIR / "manifest.json"
    if manifest_file.exists():
        return FileResponse(str(manifest_file), media_type="application/manifest+json")
    return Response(content="{}", media_type="application/manifest+json")

@app.get("/sw.js")
async def get_service_worker():
    sw_file = FRONTEND_DIR / "sw.js"
    if sw_file.exists():
        return FileResponse(str(sw_file), media_type="application/javascript")
    return Response(content="// sw", media_type="application/javascript")

# ── Primary Web Pages ──────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def root_direct(request: Request):
    """Direct root path to AI chat if no PIN required, or to welcome portal if PIN enabled."""
    host_ip, _, _ = HotspotDetector.detect_host_ip()
    host_hdr = request.headers.get("host", "").split(":")[0].strip().lower()
    
    # If the user typed an external domain (e.g. google.com, apple.com), redirect cleanly to host IP
    if host_hdr and host_hdr not in (host_ip.lower(), "127.0.0.1", "localhost", "air-ai.local", "hs-ai.local", "air.ai", "hs.ai"):
        if not re.match(r"^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)", host_hdr):
            target_path = "/welcome" if config.get("security", {}).get("require_pin", False) else "/chat"
            return RedirectResponse(url=f"http://{host_ip}{target_path}", status_code=302)

    if not config.get("security", {}).get("require_pin", False):
        chat_file = FRONTEND_DIR / "chat.html"
        if chat_file.exists():
            return FileResponse(str(chat_file), media_type="text/html")
        return HTMLResponse("<h1>AIR AI Chat</h1>")
    portal_file = FRONTEND_DIR / "portal.html"
    if portal_file.exists():
        return FileResponse(str(portal_file), media_type="text/html")
    return HTMLResponse("<h1>AIR AI Network</h1><p>Welcome Portal</p>")

@app.api_route("/welcome", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def welcome_portal(request: Request):
    """Welcome Experience / Captive Portal landing page."""
    portal_file = FRONTEND_DIR / "portal.html"
    if portal_file.exists():
        return FileResponse(str(portal_file), media_type="text/html")
    return HTMLResponse("<h1>AIR AI Network</h1><p>Welcome Portal</p>")

@app.api_route("/chat", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def chat_ui():
    """Full AIR AI Chat Interface."""
    chat_file = FRONTEND_DIR / "chat.html"
    if chat_file.exists():
        return FileResponse(str(chat_file), media_type="text/html")
    return HTMLResponse("<h1>AIR AI Chat</h1>")

@app.api_route("/dashboard", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/admin", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def host_dashboard():
    """AIR AI Host Admin Dashboard."""
    dash_file = FRONTEND_DIR / "dashboard.html"
    if dash_file.exists():
        return FileResponse(str(dash_file))
    return HTMLResponse("<h1>AIR AI Host Dashboard</h1>")

@app.get("/legacy", response_class=HTMLResponse)
async def legacy_fastchat_ui():
    """100% backward compatible FastChatUI route."""
    legacy_file = SHARED_DIR / "FastChatUI.html"
    if legacy_file.exists():
        return FileResponse(str(legacy_file))
    return RedirectResponse(url="/chat")

# ── Ollama API Reverse Proxy (Full Backward Compatibility) ─────
@app.api_route("/ollama/{path:path}", methods=["GET", "POST", "DELETE", "OPTIONS"])
async def proxy_ollama(request: Request, path: str):
    """Proxy requests to Ollama backend for legacy compatibility."""
    import urllib.request
    ollama_host = config.get("model", {}).get("ollama_host", "http://127.0.0.1:11434").rstrip("/")
    target_url = f"{ollama_host}/{path}"
    
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    
    try:
        req = urllib.request.Request(target_url, data=body if body else None, headers=headers, method=request.method)
        with urllib.request.urlopen(req, timeout=120.0) as res:
            content = res.read()
            return Response(content=content, status_code=res.status, media_type=res.headers.get("content-type"))
    except urllib.error.HTTPError as e:
        return Response(content=e.read(), status_code=e.code)
    except Exception as e:
        return Response(content=json.dumps({"error": str(e)}), status_code=502)

# ── Universal Captive Portal Fallback & Catch-All Routing ─────
@app.exception_handler(404)
async def captive_portal_404_handler(request: Request, exc):
    """
    Universal Captive Portal Fallback Handler.
    Whenever any device or browser requests any unknown URL (e.g. google.com, apple.com,
    or random deep links when opening the browser), redirect automatically to /welcome!
    """
    path = request.url.path
    # Do not redirect API, WebSocket, or Static asset 404s
    if path.startswith(("/api/", "/ws/", "/static/", "/vendor/")):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    host_ip, _, _ = HotspotDetector.detect_host_ip()
    port = request.url.port
    port_suffix = f":{port}" if port and port not in (80, 8000) else ""
    target_path = "/welcome" if config.get("security", {}).get("require_pin", False) else "/chat"
    target = f"http://{host_ip}{port_suffix}{target_path}"
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={target}">
  <title>AIR AI Network</title>
  <script>window.location.replace("{target}");</script>
</head>
<body style="font-family:sans-serif; background:#0d1117; color:#fff; text-align:center; padding:2rem;">
  <h2>AIR AI Network</h2>
  <p>Connecting to local AI appliance...</p>
  <p><a href="{target}" style="color:#2dd4bf;">Click here to enter</a></p>
</body>
</html>""",
        status_code=302,
        headers={
            "Location": target,
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }
    )

@app.api_route("/{full_path:path}", methods=["GET", "POST", "HEAD", "OPTIONS", "PUT"], response_class=HTMLResponse)
async def universal_catchall_redirect(request: Request, full_path: str):
    """Fallback catch-all route to redirect any device to /chat or /welcome."""
    if full_path.startswith(("api/", "ws/", "static/", "vendor/")):
        raise HTTPException(status_code=404, detail="Not Found")
    host_ip, _, _ = HotspotDetector.detect_host_ip()
    port = request.url.port
    port_suffix = f":{port}" if port and port not in (80, 8000) else ""
    target_path = "/welcome" if config.get("security", {}).get("require_pin", False) else "/chat"
    target = f"http://{host_ip}{port_suffix}{target_path}"
    return HTMLResponse(
        content=f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={target}"><script>window.location.replace("{target}");</script></head><body style="font-family:sans-serif;background:#090d16;color:#e2e8f0;text-align:center;padding:2rem;"><h2>AIR AI Network</h2><p>Connecting to AI appliance...</p><p><a href="{target}" style="color:#2dd4bf;">Click here to enter</a></p></body></html>',
        status_code=302,
        headers={
            "Location": target,
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

# ── Lifespan Startup & Shutdown ────────────────────────────────

mdns_instance: Optional[MDNSService] = None
dns_instance: Optional[DNSServer] = None
captive_instance: Optional[CaptivePortalServer] = None

@app.on_event("startup")
async def startup_event():
    global mdns_instance, dns_instance, captive_instance
    server_log.info("AIR AI Network Server starting up...")

    # Step 1: Detect hardware
    profile = get_complete_hardware_profile()
    ram_gb = profile["ram"]["total_gb"]
    vram_gb = profile["gpu"]["vram_total_gb"]
    server_log.info(f"Hardware Profile: RAM {ram_gb}GB | GPU {profile['gpu']['name']} ({vram_gb}GB VRAM)")

    # Step 2: Ensure inference runtime
    ensure_local_engine()

    # Step 3: Select and warm up best compatible model
    all_models = await model_manager.list_all_models()
    best = select_best_model(all_models, ram_gb, vram_gb)
    if best:
        target_model = best["id"]
        server_log.info(f"Auto-selected compatible model: {target_model}")
        asyncio.create_task(model_manager.load_model(target_model))
    else:
        server_log.warning("No compatible local models detected.")

    # Step 4: Discover Hotspot Interface & Host IP
    host_ip, adapter, is_hotspot = HotspotDetector.detect_host_ip()
    port = config.get("server", {}).get("port", 8000)
    net_log.info(f"Primary Host IP: {host_ip} ({adapter}, is_hotspot: {is_hotspot})")

    # Step 4b: Apply Captive Portal & Network Hardening (Firewall & Hosts)
    try:
        CaptiveHardener.apply_firewall_rules()
        added, msg = CaptiveHardener.harden_hosts_file(host_ip)
        net_log.info(f"Captive portal hardening: {msg}")
    except Exception as e:
        net_log.warning(f"Captive portal hardening note: {e}")

    # Step 5: Start Local RFC 1035 DNS Server on UDP port 53
    try:
        dns_instance = DNSServer(host_ip=host_ip, port=53)
        if dns_instance.start():
            app.state.dns_service = dns_instance
            net_log.info(f"Local DNS server active on UDP port 53 (Resolving to {host_ip})")
        else:
            app.state.dns_service = dns_instance
            net_log.warning(f"Local DNS standby: {dns_instance.error_message}")
    except Exception as e:
        net_log.warning(f"DNS initialization notice: {e}")

    # Step 6: Start Dedicated Captive Portal Server on TCP port 80
    try:
        captive_instance = CaptivePortalServer(
            host_ip=host_ip,
            port=80,
            api_port=port,
            base_dir=BASE_DIR,
            device_detector=device_tracker
        )
        if captive_instance.start():
            app.state.captive_portal_service = captive_instance
            net_log.info(f"Captive Portal Server active on Port 80 (Serving {host_ip})")
        else:
            app.state.captive_portal_service = captive_instance
            net_log.warning(f"Captive Portal Port 80 notice: {captive_instance.error_message}")
    except Exception as e:
        net_log.warning(f"Captive Portal initialization notice: {e}")

    # Step 7: Start mDNS discovery service
    try:
        mdns_instance = MDNSService(hostname="hs-ai.local", host_ip=host_ip)
        mdns_instance.start()
        net_log.info("mDNS service active for 'hs-ai.local'")
    except Exception as e:
        net_log.error(f"Failed to start mDNS: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    server_log.info("AIR AI Network Server shutting down...")
    if captive_instance:
        captive_instance.stop()
    if dns_instance:
        dns_instance.stop()
    if mdns_instance:
        mdns_instance.stop()
    await model_manager.unload_model()

# ── Main Entrypoint ────────────────────────────────────────────

def run_server():
    render_init_box()

    # Step 1: Hardware
    print_step(1, "Detecting hardware profile...")
    profile = get_complete_hardware_profile()
    time.sleep(0.2)

    # Step 2: Models
    print_step(2, "Scanning local model library...")
    time.sleep(0.2)

    # Step 3: Engine
    print_step(3, "Starting AI inference engine...")
    ensure_local_engine()
    time.sleep(0.2)

    # Step 4: Network & Captive Portal
    print_step(4, "Detecting Hotspot adapter & starting Captive Portal...")
    import threading as _th
    _result = ["192.168.137.1", "Wi-Fi 3", True]
    def _detect():
        try:
            r = HotspotDetector.detect_host_ip()
            _result[0], _result[1], _result[2] = r[0], r[1], r[2]
        except Exception:
            pass
    _t = _th.Thread(target=_detect, daemon=True)
    _t.start()
    _t.join(timeout=5.0)  # max 5s — never hang startup
    host_ip, adapter, is_hotspot = _result[0], _result[1], _result[2]
    port = config.get("server", {}).get("port", 8000)

    # Quick network status (non-blocking — full diagnostics available via /test/captive-portal)
    print(f"  > [Network] Hotspot IP: {host_ip} | Adapter: {adapter} | {'ONLINE' if is_hotspot else 'LAN MODE'}", flush=True)

    # Render Final Dashboard Summary
    render_ready_summary(
        model_name=config.get("model", {}).get("active_model", "Llama 3.2"),
        model_status="READY",
        hotspot_status="ONLINE" if is_hotspot else "OFFLINE",
        hotspot_ip=host_ip,
        host_port=port,
        connected_clients=len(device_tracker.list_devices()),
        drive_letter=profile.get("drive_letter", "Local")
    )

    # Open browser on host laptop
    if "--no-browser" not in sys.argv:
        def _open():
            time.sleep(1.2)
            webbrowser.open(f"http://localhost:{port}/")
        import threading
        threading.Thread(target=_open, daemon=True).start()

    # Run Uvicorn Server
    uvicorn.run(
        app,
        host=config.get("server", {}).get("host", "0.0.0.0"),
        port=port,
        log_level="warning"
    )

if __name__ == "__main__":
    run_server()
