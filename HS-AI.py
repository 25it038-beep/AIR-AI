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

from server.main import run_server

if __name__ == "__main__":
    run_server()
