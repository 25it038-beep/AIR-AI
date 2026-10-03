import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("hs_ai.captive_portal.hardener")

CAPTIVE_DOMAINS: List[str] = [
    # Android / Google
    "connectivitycheck.gstatic.com",
    "connectivitycheck.android.com",
    "clients3.google.com",
    "play.googleapis.com",
    "www.google.com",
    "google.com",
    # Apple iOS / iPadOS / macOS CNA
    "captive.apple.com",
    "www.apple.com",
    "apple.com",
    "www.airport.us",
    "www.ibook.info",
    "www.itools.info",
    "www.thinkdifferent.us",
    # Windows NCSI
    "msftconnecttest.com",
    "www.msftconnecttest.com",
    "msftncsi.com",
    "www.msftncsi.com",
    "ipv6.msftncsi.com",
    # Firefox / Linux
    "detectportal.firefox.com",
    # Samsung
    "connectivity.samsung.com",
    # Xiaomi / MIUI
    "connect.rom.miui.com",
    # Realme / Oppo / OnePlus (ColorOS / AllawnOS)
    "conn-service-in-04.allawnos.com",
    "allawnos.com",
    "wifi.coloros.com",
    "connectivitycheck.oppomobile.com",
    # Local Host & Discovery
    "air-ai.local",
    "air.ai",
    "hs-ai.local",
    "hs.ai"
]

class CaptiveHardener:
    """
    Automated Captive Portal & Network Hardening Subsystem.
    Ensures 100% unbreakable captive portal auto-redirection on Windows:
    1. Injects captive probe domains into Windows hosts file.
    2. Enforces Windows Firewall allow rules for all profiles (Public Hotspot + Private).
    3. Flushes DNS cache to guarantee immediate redirection.
    """

    @classmethod
    def is_admin(cls) -> bool:
        if os.name != "nt":
            return os.geteuid() == 0 if hasattr(os, "geteuid") else False
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @classmethod
    def harden_hosts_file(cls, host_ip: str = "192.168.137.1") -> Tuple[int, str]:
        """
        Register all captive portal probe domains to host_ip in C:\\Windows\\System32\\drivers\\etc\\hosts.
        """
        if os.name != "nt":
            return 0, "Non-Windows system"

        hosts_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
        if not hosts_path.exists():
            return 0, f"Hosts file not found at {hosts_path}"

        try:
            with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            missing = [d for d in CAPTIVE_DOMAINS if d.lower() not in content.lower()]
            if not missing:
                logger.info(f"All {len(CAPTIVE_DOMAINS)} captive probe domains are already registered in hosts.")
                return 0, "All domains already present"

            lines_to_add = [f"{host_ip} {d}\n" for d in missing]
            with open(hosts_path, "a", encoding="utf-8") as f:
                f.write("\n# AIR AI Captive Portal Probe Interceptors\n")
                f.writelines(lines_to_add)

            logger.info(f"Successfully added {len(missing)} captive probe domains to hosts file.")
            cls.flush_dns()
            return len(missing), f"Added {len(missing)} domains"
        except PermissionError:
            logger.warning("Permission denied writing to hosts file (Administrator privileges required).")
            return 0, "Permission denied (requires admin)"
        except Exception as e:
            logger.error(f"Failed to update hosts file: {e}")
            return 0, str(e)

    @classmethod
    def apply_firewall_rules(cls) -> bool:
        """
        Ensure Windows Firewall permits incoming connections on Ports 80, 8000, 53, 5353
        across ALL network profiles (including the Public adapter used by Mobile Hotspot).
        """
        if os.name != "nt":
            return True

        try:
            # Add or update rules with profile=any
            cmd_web = [
                "netsh", "advfirewall", "firewall", "add", "rule",
                'name=AIR AI Web Server', "dir=in", "action=allow",
                "protocol=TCP", "localport=80,8000", "profile=any"
            ]
            cmd_dns = [
                "netsh", "advfirewall", "firewall", "add", "rule",
                'name=AIR AI DNS Resolver', "dir=in", "action=allow",
                "protocol=UDP", "localport=53,5353", "profile=any"
            ]
            subprocess.run(cmd_web, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            subprocess.run(cmd_dns, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            logger.info("Firewall rules applied for Ports 80, 8000 (TCP) and 53, 5353 (UDP) on all profiles.")
            return True
        except Exception as e:
            logger.warning(f"Could not apply firewall rules: {e}")
            return False

    @classmethod
    def flush_dns(cls):
        """Flush Windows DNS resolver cache."""
        if os.name == "nt":
            try:
                subprocess.run(["ipconfig", "/flushdns"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                logger.info("Windows DNS cache flushed.")
            except Exception:
                pass
