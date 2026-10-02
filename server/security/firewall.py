import threading
from typing import Set

class Firewall:
    """Manages IP blocking and connection limits."""

    def __init__(self, max_clients: int = 32):
        self.blocked_ips: Set[str] = set()
        self.max_clients = max_clients
        self.active_clients: Set[str] = set()
        self.lock = threading.Lock()

    def block_ip(self, ip: str):
        with self.lock:
            self.blocked_ips.add(ip)

    def unblock_ip(self, ip: str):
        with self.lock:
            self.blocked_ips.discard(ip)

    def is_blocked(self, ip: str) -> bool:
        with self.lock:
            return ip in self.blocked_ips

    def can_connect(self, ip: str) -> bool:
        with self.lock:
            if ip in self.blocked_ips:
                return False
            # Allow loopback unconditionally
            if ip in ("127.0.0.1", "localhost", "::1"):
                return True
            if len(self.active_clients) >= self.max_clients and ip not in self.active_clients:
                return False
            self.active_clients.add(ip)
            return True

    def remove_client(self, ip: str):
        with self.lock:
            self.active_clients.discard(ip)
