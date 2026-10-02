import os
import json
import time
import socket
import threading
from typing import Dict, List, Optional
from pathlib import Path

class DeviceTracker:
    """Discovers, tracks, and manages devices connected to the HS AI Network."""

    def __init__(self, data_file: Optional[str] = None):
        self.devices: Dict[str, Dict] = {}  # ip -> device_info
        self.blocked_ips: set = set()
        self.data_file = data_file
        self.lock = threading.RLock()
        self._load_data()

    def _load_data(self):
        if not self.data_file or not os.path.exists(self.data_file):
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    self.devices = saved.get("devices", {})
                    self.blocked_ips = set(saved.get("blocked_ips", []))
        except Exception:
            pass

    def save_data(self):
        if not self.data_file:
            return
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump({
                    "devices": self.devices,
                    "blocked_ips": list(self.blocked_ips)
                }, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def parse_user_agent(ua: str) -> Dict[str, str]:
        """Classify OS, browser, and device form-factor from User-Agent."""
        if not ua:
            return {"os": "Unknown", "device_type": "Unknown", "friendly_name": "Connected Client"}

        ua_lower = ua.lower()

        # Device & OS Detection
        if "iphone" in ua_lower:
            dev_type = "Phone"
            os_name = "iOS"
            friendly = "Apple iPhone"
        elif "ipad" in ua_lower:
            dev_type = "Tablet"
            os_name = "iPadOS"
            friendly = "Apple iPad"
        elif "android" in ua_lower:
            if "mobile" in ua_lower:
                dev_type = "Phone"
                friendly = "Android Phone"
            else:
                dev_type = "Tablet"
                friendly = "Android Tablet"
            os_name = "Android"
        elif "windows" in ua_lower:
            dev_type = "Laptop / PC"
            os_name = "Windows"
            friendly = "Windows PC"
        elif "macintosh" in ua_lower or "mac os" in ua_lower:
            dev_type = "Laptop / Mac"
            os_name = "macOS"
            friendly = "MacBook / Mac"
        elif "linux" in ua_lower:
            dev_type = "Linux PC"
            os_name = "Linux"
            friendly = "Linux System"
        else:
            dev_type = "Device"
            os_name = "Unknown OS"
            friendly = "Network Client"

        return {
            "os": os_name,
            "device_type": dev_type,
            "friendly_name": friendly
        }

    def _resolve_hostname(self, ip: str) -> str:
        """Attempt safe reverse DNS lookup."""
        try:
            name, _, _ = socket.gethostbyaddr(ip)
            return name
        except Exception:
            return ip

    def register_or_update(self, ip: str, user_agent: str = "", is_authenticated: bool = False, **kwargs) -> Dict:
        """Register client visit or update last activity."""
        now = time.time()
        with self.lock:
            if ip in self.devices:
                dev = self.devices[ip]
                dev["last_activity"] = now
                dev["request_count"] = dev.get("request_count", 0) + 1
                if is_authenticated:
                    dev["is_authenticated"] = True
                if user_agent and dev.get("user_agent") != user_agent:
                    dev["user_agent"] = user_agent
                    parsed = self.parse_user_agent(user_agent)
                    dev.update(parsed)
                return dev

            # New device
            parsed = self.parse_user_agent(user_agent)
            
            # Label loopback nicely
            if ip in ("127.0.0.1", "::1", "localhost"):
                friendly = "HS AI Host (This Laptop)"
            else:
                friendly = f"{parsed['friendly_name']}"

            dev_info = {
                "ip": ip,
                "hostname": ip,
                "user_agent": user_agent,
                "os": parsed["os"],
                "device_type": parsed["device_type"],
                "friendly_name": friendly,
                "first_seen": now,
                "last_activity": now,
                "request_count": 1,
                "is_blocked": ip in self.blocked_ips,
                "is_authenticated": is_authenticated
            }
            self.devices[ip] = dev_info

        # Resolve hostname asynchronously so we don't block request
        threading.Thread(target=self._async_lookup_hostname, args=(ip,), daemon=True).start()
        self.save_data()
        return dev_info

    def _async_lookup_hostname(self, ip: str):
        hostname = self._resolve_hostname(ip)
        if hostname and hostname != ip:
            with self.lock:
                if ip in self.devices:
                    self.devices[ip]["hostname"] = hostname
            self.save_data()

    def block_device(self, ip: str):
        with self.lock:
            self.blocked_ips.add(ip)
            if ip in self.devices:
                self.devices[ip]["is_blocked"] = True
        self.save_data()

    def unblock_device(self, ip: str):
        with self.lock:
            self.blocked_ips.discard(ip)
            if ip in self.devices:
                self.devices[ip]["is_blocked"] = False
        self.save_data()

    def is_blocked(self, ip: str) -> bool:
        with self.lock:
            return ip in self.blocked_ips

    def list_devices(self) -> List[Dict]:
        """List all devices with live active/idle status."""
        now = time.time()
        result = []
        with self.lock:
            for ip, dev in self.devices.items():
                d = dict(dev)
                # Idle if no request in last 180 seconds
                d["status"] = "Active" if (now - d.get("last_activity", 0)) < 180 else "Idle"
                d["time_since_active_sec"] = round(now - d.get("last_activity", 0))
                result.append(d)
        # Sort so active devices and host are first
        result.sort(key=lambda x: (x.get("is_blocked", False), x["status"] != "Active", -x.get("last_activity", 0)))
        return result
