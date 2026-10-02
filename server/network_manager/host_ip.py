import socket
import subprocess
import re
import platform
from typing import Dict, List, Tuple

def get_network_interfaces() -> List[Dict[str, str]]:
    """List network adapters with their IPv4 addresses."""
    adapters = []
    plat = platform.system()

    if plat == "Windows":
        try:
            cmd = "powershell -NoProfile -Command \"Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress, InterfaceAlias\""
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in out.strip().splitlines()[2:]:
                parts = line.strip().split()
                if len(parts) >= 2:
                    ip = parts[0]
                    alias = " ".join(parts[1:])
                    if not ip.startswith("169.254") and ip != "127.0.0.1":
                        adapters.append({"ip": ip, "alias": alias})
        except Exception:
            pass

    # Fallback to standard socket inspection
    if not adapters:
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if not ip.startswith("127.") and not ip.startswith("169.254"):
                    adapters.append({"ip": ip, "alias": "LAN Adapter"})
        except Exception:
            pass

    return adapters

def detect_host_ip() -> Tuple[str, str, bool]:
    """
    Detect the primary host IP.
    Priority:
      1. Windows Mobile Hotspot adapter (192.168.137.x or Wi-Fi Direct virtual adapter)
      2. Active Wi-Fi / Ethernet LAN IP
      3. Fallback 127.0.0.1
    Returns: (host_ip, adapter_name, is_hotspot_ip)
    """
    adapters = get_network_interfaces()

    # 1. Look specifically for Mobile Hotspot subnet (default in Windows is 192.168.137.1)
    for a in adapters:
        if a["ip"].startswith("192.168.137.") or "wi-fi direct" in a["alias"].lower() or "hotspot" in a["alias"].lower():
            return a["ip"], a["alias"], True

    # 2. Look for regular active Wi-Fi or Ethernet
    for a in adapters:
        alias_lower = a["alias"].lower()
        if "wi-fi" in alias_lower or "ethernet" in alias_lower or "wlan" in alias_lower:
            return a["ip"], a["alias"], False

    # 3. Any non-loopback IP
    if adapters:
        return adapters[0]["ip"], adapters[0]["alias"], False

    # 4. Standard socket connection trick to get outgoing IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip, "Default Gateway", False
    except Exception:
        pass

    return "127.0.0.1", "Loopback", False
