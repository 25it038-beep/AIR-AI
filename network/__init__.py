"""
HS AI Local Captive Portal & Network Management Architecture.
Provides dedicated modules for:
 - hotspot_detector: Discovers actual Mobile Hotspot adapter & IP
 - captive_portal: Port 80 captive portal HTTP service
 - dns_server: RFC 1035 UDP 53 local DNS resolver
 - connectivity_check: Android/Apple/Windows captive probe handler & diagnostic test
 - device_detector: Client tracking and captive portal state
 - port_manager: Port conflict & availability analyzer
 - firewall_checker: Scoped Windows Firewall rule inspection & elevation helper
"""

from .hotspot_detector import HotspotDetector
from .captive_portal import CaptivePortalServer, CaptivePortalHandler
from .dns_server import DNSServer
from .connectivity_check import ConnectivityCheckManager
from .device_detector import DeviceDetector
from .port_manager import PortManager
from .firewall_checker import FirewallChecker
from . import captive_portal

__all__ = [
    "HotspotDetector",
    "CaptivePortalServer",
    "CaptivePortalHandler",
    "DNSServer",
    "ConnectivityCheckManager",
    "DeviceDetector",
    "PortManager",
    "FirewallChecker",
    "captive_portal"
]
