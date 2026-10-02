"""
HS AI Dedicated Captive Portal Package.
Architecture:
network/
└── captive_portal/
    ├── server.py        (Dedicated Port 80 Proxy / HTTP Server)
    ├── endpoints.py     (OS connectivity-check probes & welcome portal)
    ├── detector.py      (Device discovery, OS classification, probe tracking)
    ├── dns.py           (RFC 1035 UDP 53 DNS & Windows ICS fallback verification)
    └── diagnostics.py   (Real verification of complete network path)
"""

from .server import DedicatedCaptivePortalServer
from .endpoints import router as captive_router, get_portal_url, get_welcome_url
from .detector import ClientDetector
from .dns import CaptiveDNSManager
from .diagnostics import CaptivePortalDiagnostics

# Compatibility aliases
CaptivePortalServer = DedicatedCaptivePortalServer
CaptivePortalHandler = DedicatedCaptivePortalServer
DNSServer = CaptiveDNSManager
DeviceDetector = ClientDetector

__all__ = [
    "DedicatedCaptivePortalServer",
    "CaptivePortalServer",
    "CaptivePortalHandler",
    "DNSServer",
    "DeviceDetector",
    "captive_router",
    "get_portal_url",
    "get_welcome_url",
    "ClientDetector",
    "CaptiveDNSManager",
    "CaptivePortalDiagnostics"
]
