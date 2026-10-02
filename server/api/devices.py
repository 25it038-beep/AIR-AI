from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional
from pydantic import BaseModel
from ..device_manager.device_tracker import DeviceTracker
from ..security.firewall import Firewall
from ..security.auth import AuthManager
from .security_api import verify_host_admin

router = APIRouter(prefix="/api/devices", tags=["Devices"])

class DeviceActionRequest(BaseModel):
    ip: str

@router.get("")
async def get_devices(request: Request):
    """List all known and connected devices with live statuses."""
    tracker: DeviceTracker = request.app.state.device_tracker
    return {"devices": tracker.list_devices()}

@router.post("/block")
async def block_device(payload: DeviceActionRequest, request: Request, authorization: Optional[str] = Header(None)):
    """Block a device by IP address. Host administrator only."""
    verify_host_admin(request, authorization)
    tracker: DeviceTracker = request.app.state.device_tracker
    firewall: Firewall = request.app.state.firewall
    auth_mgr: AuthManager = request.app.state.auth_manager

    if payload.ip in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=400, detail="Cannot block host laptop loopback address.")

    tracker.block_device(payload.ip)
    firewall.block_ip(payload.ip)
    auth_mgr.revoke_device_sessions(payload.ip)

    return {"success": True, "ip": payload.ip, "status": "blocked"}

@router.post("/unblock")
async def unblock_device(payload: DeviceActionRequest, request: Request, authorization: Optional[str] = Header(None)):
    """Unblock a device by IP address. Host administrator only."""
    verify_host_admin(request, authorization)
    tracker: DeviceTracker = request.app.state.device_tracker
    firewall: Firewall = request.app.state.firewall

    tracker.unblock_device(payload.ip)
    firewall.unblock_ip(payload.ip)

    return {"success": True, "ip": payload.ip, "status": "unblocked"}
