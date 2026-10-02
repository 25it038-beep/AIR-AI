from .host_ip import detect_host_ip, get_network_interfaces
from .hotspot import HotspotManager
from .qr import generate_qr_svg
from .mdns import MDNSService

# Import the new local captive portal architecture
from network.hotspot_detector import HotspotDetector
from network.captive_portal import CaptivePortalServer
from network.dns_server import DNSServer
from network.connectivity_check import ConnectivityCheckManager
from network.device_detector import DeviceDetector
from network.port_manager import PortManager
from network.firewall_checker import FirewallChecker

__all__ = [
    "detect_host_ip",
    "get_network_interfaces",
    "HotspotManager",
    "generate_qr_svg",
    "MDNSService",
    "HotspotDetector",
    "CaptivePortalServer",
    "DNSServer",
    "ConnectivityCheckManager",
    "DeviceDetector",
    "PortManager",
    "FirewallChecker"
]
