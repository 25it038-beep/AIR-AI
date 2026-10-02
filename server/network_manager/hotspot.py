import platform
import subprocess
import socket
import time
from typing import Dict, Any

_hotspot_cache = None
_hotspot_cache_time = 0.0

class HotspotManager:
    """Manages detection and control of Windows Mobile Hotspot."""

    @staticmethod
    def is_windows() -> bool:
        return platform.system() == "Windows"

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Detect real hotspot status on Windows with short TTL cache."""
        global _hotspot_cache, _hotspot_cache_time
        now = time.time()
        if _hotspot_cache and (now - _hotspot_cache_time) < 6.0:
            return _hotspot_cache

        if not cls.is_windows():
            return {
                "supported": False,
                "active": False,
                "status_text": "Non-Windows OS",
                "details": "Mobile Hotspot control is only supported on Windows.",
                "manual_required": False
            }

        is_running = False
        service_status = "Stopped"
        hotspot_ip = None

        # 1. Fast native service query using sc.exe (100x faster than powershell)
        try:
            out = subprocess.check_output(["sc", "query", "icssvc"], text=True, stderr=subprocess.DEVNULL)
            if "RUNNING" in out:
                is_running = True
                service_status = "Running"
        except Exception:
            pass

        # 2. Fast pure-Python check for 192.168.137.1 IP
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if ip.startswith("192.168.137."):
                    hotspot_ip = ip
                    is_running = True
                    break
        except Exception:
            pass

        result = {
            "supported": True,
            "active": is_running,
            "status_text": "ONLINE" if is_running else "OFFLINE",
            "service_status": service_status,
            "hotspot_ip": hotspot_ip,
            "manual_required": not is_running,
            "instructions": (
                "To enable Windows Mobile Hotspot:\n"
                "1. Open Windows Settings (Win + I)\n"
                "2. Navigate to 'Network & internet' -> 'Mobile hotspot'\n"
                "3. Toggle 'Mobile hotspot' to ON\n"
                "4. Connect your phone or devices to the hotspot network."
            )
        }
        _hotspot_cache = result
        _hotspot_cache_time = now
        return result

    @classmethod
    def start_hotspot(cls) -> Dict[str, Any]:
        """Attempt to start Windows Mobile Hotspot using WinRT or netsh."""
        if not cls.is_windows():
            return {"success": False, "message": "Mobile Hotspot is only supported on Windows."}

        # Check if already active
        current = cls.get_status()
        if current["active"]:
            return {"success": True, "message": "Mobile Hotspot is already active.", "hotspot_ip": current.get("hotspot_ip")}

        # Attempt to trigger WinRT NetworkOperatorTetheringManager via PowerShell
        ps_script = """
        try {
            $profile = [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime]::GetInternetConnectionProfile()
            if ($profile) {
                $tether = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]::CreateFromConnectionProfile($profile)
                $asyncOp = $tether.StartTetheringAsync()
                $null = $asyncOp.AsTask().Wait(5000)
                Write-Output "SUCCESS"
            } else {
                Write-Output "NO_PROFILE"
            }
        } catch {
            Write-Output "ERROR: $($_.Exception.Message)"
        }
        """
        try:
            out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps_script], text=True, stderr=subprocess.DEVNULL).strip()
            if "SUCCESS" in out:
                # Re-verify
                status = cls.get_status()
                if status["active"]:
                    return {"success": True, "message": "Windows Mobile Hotspot started successfully."}
        except Exception:
            pass

        # If programmatic start is blocked by Windows UAC / group policy, provide the quick-open command
        try:
            subprocess.Popen(["start", "ms-settings:network-mobilehotspot"], shell=True)
        except Exception:
            pass

        return {
            "success": False,
            "manual_required": True,
            "message": "Windows Mobile Hotspot must be enabled manually.",
            "instructions": (
                "Windows requires user authorization for tethering.\n"
                "Settings has been opened for you, or navigate to:\n"
                "Windows Settings -> Network & internet -> Mobile hotspot -> Turn ON."
            )
        }

    @classmethod
    def stop_hotspot(cls) -> Dict[str, Any]:
        """Attempt to stop Windows Mobile Hotspot."""
        if not cls.is_windows():
            return {"success": False, "message": "Mobile Hotspot is only supported on Windows."}

        ps_script = """
        try {
            $profile = [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime]::GetInternetConnectionProfile()
            if ($profile) {
                $tether = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]::CreateFromConnectionProfile($profile)
                $asyncOp = $tether.StopTetheringAsync()
                $null = $asyncOp.AsTask().Wait(5000)
                Write-Output "SUCCESS"
            }
        } catch {
            Write-Output "ERROR"
        }
        """
        try:
            out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps_script], text=True, stderr=subprocess.DEVNULL).strip()
            if "SUCCESS" in out:
                return {"success": True, "message": "Mobile Hotspot stopped."}
        except Exception:
            pass

        return {"success": False, "message": "Could not stop hotspot automatically. Toggle off in Windows Settings."}
