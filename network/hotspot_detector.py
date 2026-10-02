import platform
import subprocess
import socket
import re
import time
from typing import Dict, List, Tuple, Any, Optional

class HotspotDetector:
    """
    Discovers the actual Windows Mobile Hotspot adapter and its IPv4 address.
    Does NOT hard-code 192.168.137.1.
    Supports dynamic subnets (192.168.137.x, 192.168.x.x, etc.) and falls back
    to physical Wi-Fi/LAN interfaces while ignoring virtual machine adapters.
    """

    _cache: Optional[Dict[str, Any]] = None
    _cache_time: float = 0.0
    CACHE_TTL: float = 4.0

    @staticmethod
    def is_windows() -> bool:
        return platform.system() == "Windows"

    @classmethod
    def get_network_interfaces(cls) -> List[Dict[str, Any]]:
        """
        Inspect all network interfaces and return valid IPv4 configurations.
        Filters out loopback, APIPA (169.254.x.x), and VirtualBox/VMware virtual adapters.
        """
        adapters = []

        # 1. psutil inspection (fast & cross-platform)
        try:
            import psutil
            for name, addrs in psutil.net_if_addrs().items():
                name_lower = name.lower()
                # Skip known virtual machine host-only adapters
                if "virtualbox" in name_lower or "vmware" in name_lower or "tap" in name_lower:
                    continue

                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        # Skip loopback and APIPA self-assigned addresses
                        if ip == "127.0.0.1" or ip.startswith("169.254."):
                            continue
                        # VirtualBox default subnet
                        if ip.startswith("192.168.56."):
                            continue

                        netmask = addr.netmask or "255.255.255.0"
                        adapters.append({
                            "name": name,
                            "ip": ip,
                            "netmask": netmask,
                            "is_hotspot_alias": any(k in name_lower for k in ("hotspot", "wi-fi direct", "local area connection*", "hostednetwork"))
                        })
        except Exception:
            pass

        # 2. Windows PowerShell Get-NetIPAddress fallback if needed
        if not adapters and cls.is_windows():
            try:
                cmd = 'powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress, InterfaceAlias"'
                out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
                for line in out.strip().splitlines()[2:]:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        ip = parts[0]
                        alias = " ".join(parts[1:])
                        alias_lower = alias.lower()
                        if ip.startswith("169.254.") or ip.startswith("127.") or ip.startswith("192.168.56."):
                            continue
                        if "virtualbox" in alias_lower or "vmware" in alias_lower:
                            continue
                        adapters.append({
                            "name": alias,
                            "ip": ip,
                            "netmask": "255.255.255.0",
                            "is_hotspot_alias": any(k in alias_lower for k in ("hotspot", "wi-fi direct", "local area connection*", "hostednetwork"))
                        })
            except Exception:
                pass

        # 3. Standard socket fallback
        if not adapters:
            try:
                hostname = socket.gethostname()
                for ip in socket.gethostbyname_ex(hostname)[2]:
                    if not ip.startswith("127.") and not ip.startswith("169.254.") and not ip.startswith("192.168.56."):
                        adapters.append({
                            "name": "Local Network",
                            "ip": ip,
                            "netmask": "255.255.255.0",
                            "is_hotspot_alias": False
                        })
            except Exception:
                pass

        return adapters

    @classmethod
    def detect_host_ip(cls) -> Tuple[str, str, bool]:
        """
        Detect the primary host IP.
        Priority:
          1. Active Windows Mobile Hotspot adapter (192.168.137.x or Wi-Fi Direct virtual adapter)
          2. Active physical Wi-Fi or WLAN adapter
          3. Active Ethernet adapter
          4. Any other non-virtual IP
          5. Fallback 127.0.0.1
        Returns: (host_ip, adapter_name, is_hotspot_active)
        """
        adapters = cls.get_network_interfaces()

        # Priority 1: Windows Mobile Hotspot default subnet or explicit Wi-Fi Direct alias
        for a in adapters:
            if a["ip"].startswith("192.168.137.") or a.get("is_hotspot_alias"):
                return a["ip"], a["name"], True

        # Priority 2: Physical Wi-Fi / WLAN adapter
        for a in adapters:
            nl = a["name"].lower()
            if "wi-fi" in nl or "wlan" in nl or "wireless" in nl:
                return a["ip"], a["name"], False

        # Priority 3: Ethernet adapter
        for a in adapters:
            nl = a["name"].lower()
            if "ethernet" in nl or "lan" in nl:
                return a["ip"], a["name"], False

        # Priority 4: Any detected adapter
        if adapters:
            return adapters[0]["ip"], adapters[0]["name"], False

        # Priority 5: Fallback socket connect trick
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip, "Default Gateway", False
        except Exception:
            pass

        return "127.0.0.1", "Loopback", False

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """
        Return comprehensive hotspot state, detected IP, and manual instructions if needed.
        Uses a short TTL cache to avoid CPU overhead from repeated queries.
        """
        now = time.time()
        if cls._cache and (now - cls._cache_time) < cls.CACHE_TTL:
            return cls._cache

        host_ip, adapter, is_hotspot = cls.detect_host_ip()
        all_adapters = cls.get_network_interfaces()

        is_running = False
        service_status = "Stopped"

        if cls.is_windows():
            # Fast check of icssvc service via sc.exe
            try:
                out = subprocess.check_output(["sc.exe", "query", "icssvc"], text=True, stderr=subprocess.DEVNULL)
                if "RUNNING" in out:
                    service_status = "Running"
                    # If hotspot adapter with IP is detected or service is running with clients
                    is_running = is_hotspot or ("192.168.137." in host_ip)
            except Exception:
                pass
        else:
            service_status = "Non-Windows"

        result = {
            "supported": cls.is_windows(),
            "active": is_running or is_hotspot,
            "status_text": "ONLINE" if (is_running or is_hotspot) else "OFFLINE",
            "service_status": service_status,
            "host_ip": host_ip,
            "adapter": adapter,
            "is_hotspot_adapter": is_hotspot,
            "hotspot_ip": host_ip if is_hotspot else ("192.168.137.1" if is_running else None),
            "all_adapters": all_adapters,
            "manual_required": not (is_running or is_hotspot),
            "instructions": (
                "To enable Windows Mobile Hotspot:\n"
                "1. Open Windows Settings (Win + I)\n"
                "2. Navigate to 'Network & internet' -> 'Mobile hotspot'\n"
                "3. Toggle 'Mobile hotspot' to ON\n"
                "4. Connect your phone or device to the hotspot network."
            )
        }

        cls._cache = result
        cls._cache_time = now
        return result
