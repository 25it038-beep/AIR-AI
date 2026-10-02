import os
import json
import time
import socket
import threading
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger("hs_ai.captive_portal.detector")

class ClientDetector:
    """
    Device discovery and classification manager for the HS AI Captive Portal.
    Detects device type, OS, hostname, captive portal interaction status, and active state.
    Classifies connectivity cases:
      Case A: Device cannot reach host
      Case B: Device reaches host but connectivity check not intercepted
      Case C: Connectivity check intercepted but OS did not launch portal window
      Case D: Portal opens successfully
    """

    def __init__(self, data_file: Optional[str] = None):
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.blocked_ips: set = set()
        self.probe_history: List[Dict[str, Any]] = []
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
                    self.probe_history = saved.get("probe_history", [])[-50:]
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
                    "blocked_ips": list(self.blocked_ips),
                    "probe_history": self.probe_history[-50:]
                }, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def parse_user_agent(ua: str) -> Dict[str, Any]:
        """Classify OS, browser, device form-factor, and specific Android/iOS version from User-Agent."""
        if not ua:
            return {
                "os": "Unknown OS",
                "os_family": "Unknown",
                "os_version": "Unknown",
                "device_type": "Device",
                "friendly_name": "Network Client"
            }

        ua_lower = ua.lower()
        dev_type = "Device"
        os_name = "Connected OS"
        os_family = "Unknown"
        os_version = "Unknown"
        friendly = "Network Device"

        # Android Detection
        if "android" in ua_lower:
            os_family = "Android"
            dev_type = "Phone" if "mobile" in ua_lower else "Tablet"
            # Extract Android version
            import re
            m = re.search(r"android\s+([\d\.]+)", ua_lower)
            if m:
                os_version = f"Android {m.group(1)}"
                os_name = os_version
            else:
                os_name = "Android"

            # Check specific brand/model
            if "pixel" in ua_lower:
                friendly = "Google Pixel"
            elif "samsung" in ua_lower or "sm-" in ua_lower:
                friendly = "Samsung Galaxy"
            elif "rmx" in ua_lower or "realme" in ua_lower:
                friendly = "Realme Device"
            elif "oneplus" in ua_lower or "cph" in ua_lower:
                friendly = "OnePlus / Oppo Phone"
            elif "oppo" in ua_lower:
                friendly = "Oppo Phone"
            elif "vivo" in ua_lower or "iqoo" in ua_lower:
                friendly = "Vivo / iQOO Phone"
            elif "xiaomi" in ua_lower or "redmi" in ua_lower or "poco" in ua_lower or "miui" in ua_lower:
                friendly = "Xiaomi / Redmi Phone"
            elif "huawei" in ua_lower or "honor" in ua_lower:
                friendly = "Huawei / Honor Phone"
            elif "moto" in ua_lower or "motorola" in ua_lower:
                friendly = "Motorola Phone"
            else:
                friendly = "Android Phone" if dev_type == "Phone" else "Android Tablet"

        # Amazon Kindle / Fire OS
        elif "kindle" in ua_lower or "silk" in ua_lower:
            os_family = "Fire OS"
            dev_type = "E-Reader / Tablet"
            os_name = "Amazon Fire OS"
            friendly = "Amazon Kindle / Fire Tablet"
        elif "iphone" in ua_lower:
            os_family = "iOS"
            dev_type = "Phone"
            os_name = "iOS"
            friendly = "Apple iPhone"
        elif "ipad" in ua_lower:
            os_family = "iOS"
            dev_type = "Tablet"
            os_name = "iPadOS"
            friendly = "Apple iPad"
        elif "captivenetworksupport" in ua_lower:
            os_family = "iOS"
            dev_type = "Phone / Tablet"
            os_name = "Apple CNA"
            friendly = "Apple Device (Captive Assistant)"
        elif "macintosh" in ua_lower or "mac os" in ua_lower:
            os_family = "macOS"
            dev_type = "Laptop / Mac"
            os_name = "macOS"
            friendly = "Apple Mac"

        # Windows
        elif "windows" in ua_lower:
            os_family = "Windows"
            dev_type = "Laptop / PC"
            os_name = "Windows"
            friendly = "Windows PC"

        # ChromeOS / Linux
        elif "cros" in ua_lower:
            os_family = "ChromeOS"
            dev_type = "Chromebook"
            os_name = "ChromeOS"
            friendly = "Chromebook"
        elif "linux" in ua_lower:
            os_family = "Linux"
            dev_type = "Linux PC"
            os_name = "Linux"
            friendly = "Linux System"

        return {
            "os": os_name,
            "os_family": os_family,
            "os_version": os_version,
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

    def register_or_update(self, ip: str, user_agent: str = "", is_authenticated: bool = False, **kwargs) -> Dict[str, Any]:
        """Register device connection or update activity timestamp."""
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
                    dev["os"] = parsed["os"]
                    dev["os_family"] = parsed["os_family"]
                    dev["device_type"] = parsed["device_type"]
                    if not dev.get("custom_name"):
                        dev["friendly_name"] = parsed["friendly_name"]
                return dev

            parsed = self.parse_user_agent(user_agent)
            if ip in ("127.0.0.1", "::1", "localhost"):
                friendly = "HS AI Host (This Laptop)"
            else:
                friendly = parsed["friendly_name"]

            dev_info = {
                "ip": ip,
                "hostname": ip,
                "user_agent": user_agent,
                "os": parsed["os"],
                "os_family": parsed["os_family"],
                "os_version": parsed["os_version"],
                "device_type": parsed["device_type"],
                "friendly_name": friendly,
                "first_seen": now,
                "last_activity": now,
                "request_count": 1,
                "is_blocked": ip in self.blocked_ips,
                "is_authenticated": is_authenticated,
                "captive_portal_served": False,
                "captive_portal_time": None,
                "last_probe_endpoint": None,
                "diagnostic_case": "Case A (Pending probe)"
            }
            self.devices[ip] = dev_info

        threading.Thread(target=self._async_lookup_hostname, args=(ip,), daemon=True).start()
        self.save_data()
        return dev_info

    def record_captive_hit(self, ip: str, endpoint: str, user_agent: str = "", status_code: int = 302, client_family: str = ""):
        """
        Record that a captive portal probe or landing page was served to this device.
        Updates diagnostic state (Case B -> Case C / Case D).
        """
        now = time.time()
        timestr = time.strftime("%H:%M:%S", time.localtime(now))
        parsed = self.parse_user_agent(user_agent)
        family = client_family or parsed["os_family"]

        with self.lock:
            if ip not in self.devices:
                self.register_or_update(ip, user_agent)

            if ip in self.devices:
                dev = self.devices[ip]
                dev["captive_portal_served"] = True
                dev["captive_portal_time"] = now
                dev["last_probe_endpoint"] = endpoint
                dev["last_activity"] = now
                dev["request_count"] = dev.get("request_count", 0) + 1

                # Advance diagnostic case
                if endpoint in ("/welcome", "/", "/chat"):
                    dev["diagnostic_case"] = "Case D (Portal Opened Successfully)"
                else:
                    dev["diagnostic_case"] = "Case C (Probe Intercepted - Awaiting OS Portal Window)"

                if user_agent and not dev.get("user_agent"):
                    dev["user_agent"] = user_agent
                    dev["os"] = parsed["os"]
                    dev["os_family"] = parsed["os_family"]
                    dev["device_type"] = parsed["device_type"]
                    dev["friendly_name"] = parsed["friendly_name"]

            # Log to probe history
            self.probe_history.append({
                "time": timestr,
                "timestamp": now,
                "ip": ip,
                "endpoint": endpoint,
                "client": family,
                "status_code": status_code
            })
            if len(self.probe_history) > 100:
                self.probe_history = self.probe_history[-100:]

        self.save_data()

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

    def update_friendly_name(self, ip: str, name: str):
        with self.lock:
            if ip in self.devices:
                self.devices[ip]["friendly_name"] = name
                self.devices[ip]["custom_name"] = True
        self.save_data()

    def list_devices(self) -> List[Dict[str, Any]]:
        now = time.time()
        result = []
        with self.lock:
            for ip, dev in self.devices.items():
                d = dict(dev)
                d["status"] = "Active" if (now - d.get("last_activity", 0)) < 180 else "Idle"
                d["time_since_active_sec"] = round(now - d.get("last_activity", 0))
                result.append(d)
        result.sort(key=lambda x: (x["status"] != "Active", x.get("is_blocked", False), -x.get("last_activity", 0)))
        return result

    def get_summary(self) -> Dict[str, Any]:
        """Summary for diagnostics and dashboard."""
        now = time.time()
        with self.lock:
            active_count = sum(1 for d in self.devices.values() if (now - d.get("last_activity", 0)) < 180)
            captive_served_count = sum(1 for d in self.devices.values() if d.get("captive_portal_served"))
            recent_probes = self.probe_history[-10:]
            return {
                "total_devices": len(self.devices),
                "active_devices": active_count,
                "captive_portal_served_count": captive_served_count,
                "recent_probes": recent_probes,
                "has_detected_checks": len(self.probe_history) > 0
            }
