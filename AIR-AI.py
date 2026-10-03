#!/usr/bin/env python3
"""
AIR AI Network Launcher
One-click entry point for AIR AI Host Appliance.
"""
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import importlib
hs_ai = importlib.import_module("HS-AI")

if __name__ == "__main__":
    if hasattr(hs_ai, "request_admin_elevation"):
        hs_ai.request_admin_elevation()
    from server.main import run_server
    run_server()
