import time
import secrets
import threading
import logging
from typing import Dict, Optional, Any, List
logger = logging.getLogger("hs_ai.security.auth")

class SessionToken(str):
    """String token subclass that allows dict-like field access for backward compatibility."""
    def __new__(cls, token: str, session_data: dict):
        obj = str.__new__(cls, token)
        obj._data = session_data
        return obj

    def __getitem__(self, item):
        return self._data[item]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def to_dict(self):
        return dict(self._data)

class AuthManager:
    """
    Production-grade Network Authentication and Session Management for HS AI.
    Implements:
      - Cryptographically secure 6-digit Network PIN with expiration & renewal.
      - Isolated host administrator credentials.
      - Full session lifecycle: creation, validation, idle-timeout, sliding expiration,
        revocation, and maximum session capping.
      - Host-only privilege enforcement for sensitive admin controls.
    """

    def __init__(
        self,
        require_pin: bool = False,
        network_pin: Optional[str] = None,
        pin_validity_minutes: int = 30,
        session_ttl_hours: int = 4,
        idle_timeout_minutes: int = 30,
        max_active_sessions: int = 64
    ):
        self.require_pin = require_pin
        self.pin_validity_seconds = pin_validity_minutes * 60
        self.session_ttl_seconds = session_ttl_hours * 3600
        self.idle_timeout_seconds = idle_timeout_minutes * 60
        self.max_active_sessions = max_active_sessions

        # Dedicated Host Administrator Token (Loopback / Host Dashboard)
        self.host_token = secrets.token_urlsafe(32)

        # Generate initial random 6-digit PIN or use provided
        self.network_pin = str(network_pin) if network_pin else self._generate_secure_pin()
        self.pin_created_at = time.time()
        self.pin_expires_at = self.pin_created_at + self.pin_validity_seconds

        # In-memory session store: session_token -> Session Dict
        # Key fields: session_id, device_id, client_ip, user_agent, created_at, expires_at, last_activity, permissions, is_host
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()

        logger.info(f"AuthManager initialized. PIN Required: {self.require_pin}, Initial PIN: {self.network_pin}")

    def _generate_secure_pin(self) -> str:
        """Generate a cryptographically secure 6-digit PIN (100000 - 999999)."""
        return str(secrets.randbelow(900000) + 100000)

    def generate_new_pin(self, validity_minutes: Optional[int] = None) -> str:
        """Regenerate the network PIN with a fresh expiration window."""
        with self.lock:
            if validity_minutes:
                self.pin_validity_seconds = validity_minutes * 60
            self.network_pin = self._generate_secure_pin()
            self.pin_created_at = time.time()
            self.pin_expires_at = self.pin_created_at + self.pin_validity_seconds
            logger.info(f"New network PIN generated: {self.network_pin} (expires in {self.pin_validity_seconds // 60}m)")
            return self.network_pin

    def set_require_pin(self, required: bool):
        """Toggle network PIN requirement on or off."""
        with self.lock:
            self.require_pin = required
            logger.info(f"Network PIN requirement set to: {self.require_pin}")

    def get_pin_status(self) -> Dict[str, Any]:
        """Return current PIN status, remaining time, and requirement state."""
        with self.lock:
            now = time.time()
            remaining = max(0, int(self.pin_expires_at - now))
            expired = remaining <= 0
            if expired and self.require_pin:
                # Auto-renew expired PIN so users don't get locked out indefinitely
                self.generate_new_pin()
                remaining = self.pin_validity_seconds
                expired = False

            return {
                "require_pin": self.require_pin,
                "current_pin": self.network_pin,
                "expires_in_seconds": remaining,
                "expires_at_timestamp": self.pin_expires_at,
                "is_expired": expired,
                "active_sessions_count": len(self.sessions)
            }

    def verify_pin(self, entered_pin: str) -> bool:
        """Validate an entered PIN against the active, unexpired network PIN."""
        if not self.require_pin:
            return True

        with self.lock:
            now = time.time()
            if now > self.pin_expires_at:
                logger.warning("Attempted PIN verification against expired PIN.")
                return False

            entered = str(entered_pin or "").strip()
            # Constant-time comparison to prevent timing attacks
            return secrets.compare_digest(entered, self.network_pin)

    def create_session(
        self,
        client_ip: str,
        user_agent: str = "",
        device_id: Optional[str] = None,
        is_host: bool = False
    ) -> Dict[str, Any]:
        """Create a new authenticated session for a client device."""
        with self.lock:
            self._cleanup_expired_sessions()

            # Enforce max sessions cap: evict oldest idle session if at capacity
            if len(self.sessions) >= self.max_active_sessions:
                oldest_token = min(
                    self.sessions.keys(),
                    key=lambda t: self.sessions[t].get("last_activity", 0)
                )
                logger.info(f"Evicting oldest idle session: {oldest_token[:8]}...")
                del self.sessions[oldest_token]

            now = time.time()
            token = secrets.token_urlsafe(32)
            dev_id = device_id or f"dev_{secrets.token_hex(6)}"

            session_record = {
                "session_id": token,
                "device_id": dev_id,
                "client_ip": client_ip,
                "user_agent": user_agent[:250],
                "created_at": now,
                "expires_at": now + self.session_ttl_seconds,
                "last_activity": now,
                "is_host": is_host,
                "permissions": {
                    "chat": True,
                    "upload": True,
                    "admin": is_host
                }
            }
            self.sessions[token] = session_record
            logger.info(f"Session created for {client_ip} ({dev_id}). Token: {token[:8]}...")
            return SessionToken(token, session_record)

    def get_session(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Retrieve active session record by token if valid and unexpired."""
        if not token:
            return None

        with self.lock:
            session = self.sessions.get(token)
            if not session:
                return None

            now = time.time()
            # Check hard expiration
            if now > session.get("expires_at", 0):
                logger.info(f"Session {token[:8]} hard-expired.")
                del self.sessions[token]
                return None

            # Check idle timeout
            if (now - session.get("last_activity", 0)) > self.idle_timeout_seconds:
                logger.info(f"Session {token[:8]} idle-expired.")
                del self.sessions[token]
                return None

            # Update last activity (sliding window)
            session["last_activity"] = now
            return session

    def is_valid_session(self, token: Optional[str], client_ip: str) -> bool:
        """Validate if a session token is active, matches client IP, and is unexpired."""
        if not self.require_pin:
            # If PIN authentication is disabled by host, loopback & local clients are allowed
            return True

        if not token:
            return False

        session = self.get_session(token)
        if not session:
            return False

        # Verify client IP matches session origin
        if session.get("client_ip") != client_ip and client_ip not in ("127.0.0.1", "localhost", "::1"):
            logger.warning(f"Session IP mismatch: token bound to {session.get('client_ip')}, request from {client_ip}")
            return False

        return True

    def revoke_session(self, token: str) -> bool:
        """Revoke and delete a specific session."""
        with self.lock:
            if token in self.sessions:
                del self.sessions[token]
                logger.info(f"Session {token[:8]} manually revoked.")
                return True
            return False

    def revoke_device_sessions(self, client_ip: str) -> int:
        """Revoke all sessions associated with an IP address (device block/disconnect)."""
        with self.lock:
            to_remove = [t for t, s in self.sessions.items() if s.get("client_ip") == client_ip]
            for t in to_remove:
                del self.sessions[t]
            if to_remove:
                logger.info(f"Revoked {len(to_remove)} sessions for device IP {client_ip}.")
            return len(to_remove)

    def is_host(self, token: Optional[str], client_ip: str) -> bool:
        """
        Check if request has host administrator privileges.
        Host is strictly defined as loopback (127.0.0.1, ::1) OR providing the valid host_token.
        Connected devices on the hotspot (192.168.137.x) NEVER have host privileges by default.
        """
        if client_ip in ("127.0.0.1", "localhost", "::1"):
            return True
        if token and secrets.compare_digest(token, self.host_token):
            return True
        session = self.get_session(token) if token else None
        return bool(session and session.get("is_host"))

    def list_active_sessions(self) -> List[Dict[str, Any]]:
        """List sanitized session summaries for host management dashboard."""
        with self.lock:
            self._cleanup_expired_sessions()
            now = time.time()
            results = []
            for token, s in self.sessions.items():
                results.append({
                    "session_id_short": token[:8] + "...",
                    "token": token,
                    "device_id": s.get("device_id", "unknown"),
                    "client_ip": s.get("client_ip", "unknown"),
                    "user_agent": s.get("user_agent", ""),
                    "created_at": s.get("created_at", 0),
                    "last_active": s.get("last_activity", 0),
                    "idle_seconds": int(now - s.get("last_activity", now)),
                    "expires_in_seconds": max(0, int(s.get("expires_at", now) - now)),
                    "is_host": s.get("is_host", False),
                    "status": "Active" if (now - s.get("last_activity", now)) < 120 else "Idle"
                })
            return results

    def _cleanup_expired_sessions(self):
        """Internal routine to purge expired sessions."""
        now = time.time()
        to_del = []
        for token, s in self.sessions.items():
            if now > s.get("expires_at", 0) or (now - s.get("last_activity", 0)) > self.idle_timeout_seconds:
                to_del.append(token)
        for t in to_del:
            del self.sessions[t]

    def invalidate_all_on_stop(self):
        """Invalidate all sessions and PINs when host service shuts down."""
        with self.lock:
            self.sessions.clear()
            self.network_pin = ""
            logger.info("All active sessions and PINs purged on service shutdown.")
