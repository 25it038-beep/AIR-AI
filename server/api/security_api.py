import time
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel

from ..security.auth import AuthManager
from ..security.rate_limiter import RateLimiter
from ..security.firewall import Firewall
from ..device_manager.device_tracker import DeviceTracker

logger = logging.getLogger("hs_ai.api.security")

router = APIRouter(prefix="/api", tags=["Security & Auth"])

class PinLoginRequest(BaseModel):
    pin: str
    device_id: Optional[str] = None
    client_name: Optional[str] = None

class PinToggleRequest(BaseModel):
    require_pin: bool

class SessionRevokeRequest(BaseModel):
    token: str

class DeviceBlockRequest(BaseModel):
    ip: str

# ── Helper to extract client token ──────────────────────────────
def get_request_token(request: Request, authorization: Optional[str] = None) -> Optional[str]:
    """Extract token from Authorization header (Bearer), cookie, or query parameter."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.split("Bearer ")[1].strip()
    
    # Check Cookie
    token = request.cookies.get("hs_session")
    if token:
        return token
        
    # Check Query Parameter
    return request.query_params.get("token")

# ── Client Auth Endpoints ───────────────────────────────────────

@router.get("/auth/status")
async def get_auth_status(request: Request, authorization: Optional[str] = Header(None)):
    """
    Check if authentication is required and if the current client session is active.
    Publicly accessible from local hotspot.
    """
    auth_mgr: AuthManager = request.app.state.auth_manager
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")

    token = get_request_token(request, authorization)
    session = auth_mgr.get_session(token) if token else None
    is_authenticated = bool(session) if auth_mgr.require_pin else True

    return {
        "require_pin": auth_mgr.require_pin,
        "is_authenticated": is_authenticated,
        "client_ip": client_ip,
        "is_host": auth_mgr.is_host(token, client_ip),
        "session": {
            "session_id_short": (session["session_id"][:8] + "...") if session else None,
            "device_id": session.get("device_id") if session else None,
            "expires_in_seconds": max(0, int(session["expires_at"] - time.time())) if session else 0
        } if session else None
    }

@router.post("/auth/login")
async def login_with_pin(payload: PinLoginRequest, request: Request):
    """
    Authenticate a new device with the 6-digit Network PIN.
    Rate-limited to 5 attempts/minute per IP.
    """
    auth_mgr: AuthManager = request.app.state.auth_manager
    rate_limiter: RateLimiter = request.app.state.rate_limiter
    device_tracker: DeviceTracker = request.app.state.device_tracker

    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
    user_agent = request.headers.get("user-agent", "")

    # Rate limiting on auth attempts
    allowed, retry_after = rate_limiter.check_rate_limit(client_ip, "auth")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many authentication attempts. Please wait {retry_after} seconds before trying again."
        )

    # Verify PIN
    if not auth_mgr.verify_pin(payload.pin):
        logger.warning(f"Failed PIN authentication attempt from {client_ip}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired network PIN. Please check the host dashboard for the current PIN."
        )

    # Register/Update device
    device_tracker.register_or_update(client_ip, user_agent, is_authenticated=True)
    if payload.client_name and hasattr(device_tracker, "update_friendly_name"):
        device_tracker.update_friendly_name(client_ip, payload.client_name)

    # Create new session
    is_host = (client_ip in ("127.0.0.1", "localhost", "::1"))
    session = auth_mgr.create_session(
        client_ip=client_ip,
        user_agent=user_agent,
        device_id=payload.device_id,
        is_host=is_host
    )

    logger.info(f"Client {client_ip} successfully authenticated with network PIN.")
    return {
        "success": True,
        "token": session["session_id"],
        "device_id": session["device_id"],
        "expires_at": session["expires_at"],
        "message": "Welcome to AIR AI Network. Secure session established."
    }

@router.post("/auth/logout")
async def logout(request: Request, authorization: Optional[str] = Header(None)):
    """Terminate the current client session."""
    auth_mgr: AuthManager = request.app.state.auth_manager
    token = get_request_token(request, authorization)
    if token:
        auth_mgr.revoke_session(token)
    return {"success": True, "message": "Logged out successfully."}

# ── Host Admin Endpoints (Host Loopback or Host Token Only) ─────

def verify_host_admin(request: Request, authorization: Optional[str] = None):
    """Ensure caller is the physical host laptop or holds valid host_token."""
    auth_mgr: AuthManager = request.app.state.auth_manager
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
    token = get_request_token(request, authorization) or request.headers.get("x-host-admin-token")

    if not auth_mgr.is_host(token, client_ip):
        logger.warning(f"Unauthorized host admin attempt from {client_ip}")
        raise HTTPException(
            status_code=403,
            detail="Access denied. This action requires AIR AI Host administrator privileges."
        )

@router.get("/admin/pin")
async def get_admin_pin_status(request: Request, authorization: Optional[str] = Header(None)):
    """Get active network PIN and remaining expiration window. Host-only."""
    verify_host_admin(request, authorization)
    auth_mgr: AuthManager = request.app.state.auth_manager
    return auth_mgr.get_pin_status()

@router.post("/admin/pin/generate")
async def generate_new_admin_pin(request: Request, authorization: Optional[str] = Header(None)):
    """Generate a fresh random 6-digit network PIN. Host-only."""
    verify_host_admin(request, authorization)
    auth_mgr: AuthManager = request.app.state.auth_manager
    new_pin = auth_mgr.generate_new_pin()
    return {
        "success": True,
        "new_pin": new_pin,
        "status": auth_mgr.get_pin_status()
    }

@router.post("/admin/pin/toggle")
async def toggle_pin_requirement(payload: PinToggleRequest, request: Request, authorization: Optional[str] = Header(None)):
    """Enable or disable network PIN requirement. Host-only."""
    verify_host_admin(request, authorization)
    auth_mgr: AuthManager = request.app.state.auth_manager
    auth_mgr.set_require_pin(payload.require_pin)
    return {
        "success": True,
        "require_pin": auth_mgr.require_pin,
        "status": auth_mgr.get_pin_status()
    }

@router.get("/admin/sessions")
async def get_admin_sessions(request: Request, authorization: Optional[str] = Header(None)):
    """List all active client sessions. Host-only."""
    verify_host_admin(request, authorization)
    auth_mgr: AuthManager = request.app.state.auth_manager
    return {"sessions": auth_mgr.list_active_sessions()}

@router.post("/admin/sessions/revoke")
async def revoke_client_session(payload: SessionRevokeRequest, request: Request, authorization: Optional[str] = Header(None)):
    """Revoke a specific active session. Host-only."""
    verify_host_admin(request, authorization)
    auth_mgr: AuthManager = request.app.state.auth_manager
    revoked = auth_mgr.revoke_session(payload.token)
    return {"success": revoked, "token": payload.token}

@router.get("/admin/security/overview")
async def get_security_overview(request: Request, authorization: Optional[str] = Header(None)):
    """Full security posture overview for host dashboard. Host-only."""
    verify_host_admin(request, authorization)
    auth_mgr: AuthManager = request.app.state.auth_manager
    rate_limiter: RateLimiter = request.app.state.rate_limiter
    firewall: Firewall = request.app.state.firewall

    return {
        "local_network_only": True,
        "public_internet_exposed": False,
        "authentication_enabled": auth_mgr.require_pin,
        "active_pin": auth_mgr.network_pin if auth_mgr.require_pin else None,
        "pin_expires_in": max(0, int(auth_mgr.pin_expires_at - time.time())),
        "rate_limiting_active": True,
        "rate_limits": rate_limiter.get_stats(),
        "active_sessions_count": len(auth_mgr.sessions),
        "blocked_ips_count": len(firewall.blocked_ips),
        "device_isolation": True
    }

