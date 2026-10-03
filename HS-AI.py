#!/usr/bin/env python3
"""
AIR AI Network Launcher
One-click entry point for AIR AI Host Appliance.
"""
import os
import sys
import ctypes
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def request_admin_elevation():
    """Request UAC administrator elevation on Windows if not already elevated."""
    if sys.platform == "win32" and not is_admin():
        try:
            params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
            if getattr(sys, "frozen", False):
                ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
            else:
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, f'"{os.path.abspath(sys.argv[0])}" {params}'.strip(), None, 1
                )
            if int(ret) > 32:
                sys.exit(0)
        except Exception as e:
            print(f"[!] UAC elevation notice: {e}")

if __name__ == "__main__":
    try:
        request_admin_elevation()
        from server.main import run_server
        run_server()
    except KeyboardInterrupt:
        print("\n[AIR AI] Stopped by user.")
        sys.exit(0)
    except Exception as e:
        import traceback
        print("\n" + "=" * 55)
        print(" [AIR AI CRITICAL ERROR] An error occurred during startup:")
        print("=" * 55)
        traceback.print_exc()
        print("=" * 55)
        try:
            input("\nPress Enter to exit...")
        except Exception:
            pass
        sys.exit(1)
