"""
Captive Portal API Router for FastAPI.
Exposes endpoints defined in the dedicated network.captive_portal module.
"""

from network.captive_portal.endpoints import (
    router,
    get_portal_url,
    get_welcome_url,
    android_captive_check,
    apple_cna_hotspot,
    windows_connect_test,
    generic_portal_redirect,
    generic_probe,
    welcome_page,
    connectivity_check_api,
    captive_portal_test_page
)

__all__ = [
    "router",
    "get_portal_url",
    "get_welcome_url"
]
