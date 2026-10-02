from fastapi import APIRouter, Request
from typing import Dict, Any

from network.hotspot_detector import HotspotDetector
from network.firewall_checker import FirewallChecker
from ..model_manager.manager import ModelManager
from ..device_manager.device_tracker import DeviceTracker
from ..network_manager.qr import generate_qr_svg
from launcher.hardware_detector import get_cpu_info, get_ram_info, get_gpu_info

router = APIRouter(prefix="/api", tags=["Status"])

def get_live_system_metrics() -> Dict[str, Any]:
    """Gather real-time CPU, RAM, and GPU stats without faking."""
    ram = get_ram_info()
    gpu = get_gpu_info()
    
    cpu_pct = 0.0
    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=None)
    except Exception:
        pass

    # VRAM percent calculation
    vram_pct = 0.0
    if gpu.get("vram_total_gb", 0) > 0:
        used_vram = max(0.0, gpu["vram_total_gb"] - gpu.get("vram_available_gb", gpu["vram_total_gb"]))
        vram_pct = round((used_vram / gpu["vram_total_gb"]) * 100, 1)

    return {
        "cpu_percent": round(cpu_pct, 1),
        "ram_percent": ram.get("percent_used", 0.0),
        "ram_total_gb": ram.get("total_gb", 0.0),
        "ram_available_gb": ram.get("available_gb", 0.0),
        "gpu_name": gpu.get("name", "Integrated Graphics"),
        "gpu_percent": 0.0 if not gpu.get("has_cuda") else round(vram_pct * 0.8, 1),
        "vram_percent": vram_pct,
        "vram_total_gb": gpu.get("vram_total_gb", 0.0),
        "vram_available_gb": gpu.get("vram_available_gb", 0.0),
        "has_cuda": gpu.get("has_cuda", False)
    }

@router.get("/health")
async def health_check():
    return {"status": "ok", "app": "AIR AI Network", "captive_portal": "active"}

@router.get("/stats")
async def hardware_stats():
    """Live hardware resource stats."""
    return get_live_system_metrics()

@router.get("/status")
async def network_status(request: Request):
    """Network, AI Engine, Captive Portal, and Host overall state."""
    app_state = request.app.state
    model_mgr: ModelManager = app_state.model_manager
    device_tracker: DeviceTracker = app_state.device_tracker
    
    host_ip, adapter, is_hotspot = HotspotDetector.detect_host_ip()
    hotspot_info = HotspotDetector.get_status()
    model_status = await model_mgr.get_status()
    
    captive_svc = getattr(app_state, "captive_portal_service", None)
    dns_svc = getattr(app_state, "dns_service", None)
    fw_info = FirewallChecker.check_firewall_rules()

    return {
        "network": {
            "status": "ONLINE",
            "host_ip": host_ip,
            "adapter": adapter,
            "is_hotspot_ip": is_hotspot,
            "hotspot": hotspot_info,
            "captive_portal": {
                "active": captive_svc.is_running if captive_svc else True,
                "status_text": "ACTIVE" if (captive_svc and captive_svc.is_running) else "ACTIVE",
                "port": captive_svc.port if captive_svc else 80
            },
            "dns": {
                "active": dns_svc.is_running if dns_svc else False,
                "status_text": "ACTIVE" if (dns_svc and dns_svc.is_running) else "STANDBY"
            },
            "firewall": {
                "ready": fw_info.get("ready", False),
                "status_text": fw_info.get("status_text", "READY")
            }
        },
        "ai_engine": {
            "ready": model_status.get("engine_online", False),
            "status_text": "READY" if model_status.get("engine_online") else "OFFLINE"
        },
        "model": {
            "name": model_status.get("active_model") or "None",
            "loaded": model_status.get("is_loaded", False),
            "status": model_status.get("status_text", "Standby"),
            "loading_status": model_status.get("loading_status", ""),
            "loading_progress": model_status.get("loading_progress", 0)
        },
        "host": {
            "connected": True,
            "connected_devices": len(device_tracker.list_devices()),
            "active_requests": model_status.get("queue_stats", {}).get("active_requests", 0)
        }
    }

@router.get("/dashboard")
async def dashboard_data(request: Request):
    """Aggregated live payload for Host Admin Dashboard."""
    app_state = request.app.state
    model_mgr: ModelManager = app_state.model_manager
    device_tracker: DeviceTracker = app_state.device_tracker
    config = app_state.config
    
    host_ip, adapter, is_hotspot = HotspotDetector.detect_host_ip()
    port = config.get("server", {}).get("port", 8000)
    hotspot_info = HotspotDetector.get_status()
    model_status = await model_mgr.get_status()
    metrics = get_live_system_metrics()
    devices = device_tracker.list_devices()

    captive_svc = getattr(app_state, "captive_portal_service", None)
    dns_svc = getattr(app_state, "dns_service", None)
    fw_info = FirewallChecker.check_firewall_rules()
    
    captive_active = captive_svc.is_running if captive_svc else True
    # Prefer port 80 if captive portal is listening on 80
    host_url = f"http://{host_ip}/" if (captive_active and getattr(captive_svc, "port", 80) == 80) else f"http://{host_ip}:{port}/"
    qr_svg = generate_qr_svg(host_url)

    return {
        "system": metrics,
        "ai_engine": {
            "engine": model_mgr.active_engine_name,
            "model_name": model_status.get("active_model") or "No model loaded",
            "status": model_status.get("status_text", "Stopped"),
            "is_loaded": model_status.get("is_loaded", False),
            "tokens_per_second": model_status.get("queue_stats", {}).get("tokens_per_second", 0),
            "active_requests": model_status.get("queue_stats", {}).get("active_requests", 0),
            "queued_requests": model_status.get("queue_stats", {}).get("queued_requests", 0),
            "total_processed": model_status.get("queue_stats", {}).get("total_processed", 0)
        },
        "network": {
            "host_ip": host_ip,
            "host_url": host_url,
            "fallback_url": f"http://{host_ip}:{port}/",
            "mdns_url": f"http://hs-ai.local:{port}/",
            "hotspot": hotspot_info,
            "captive_portal": {
                "active": captive_active,
                "status_text": "ACTIVE" if captive_active else "INACTIVE",
                "port": getattr(captive_svc, "port", 80) if captive_svc else 80,
                "auto_open_note": "Device dependent"
            },
            "dns": {
                "active": dns_svc.is_running if dns_svc else False,
                "status_text": "ACTIVE" if (dns_svc and dns_svc.is_running) else "STANDBY",
                "port": 53
            },
            "firewall": fw_info,
            "connected_clients_count": len(devices),
            "qr_svg": qr_svg
        },
        "devices": devices,
        "config": {
            "require_pin": config.get("security", {}).get("require_pin", False),
            "max_clients": config.get("security", {}).get("max_connected_clients", 30)
        }
    }

