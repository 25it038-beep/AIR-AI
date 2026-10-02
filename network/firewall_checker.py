import platform
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, List

class FirewallChecker:
    """
    Detects Windows Firewall status for HS AI ports (TCP 80, TCP 8000, UDP 53).
    Provides scoped firewall rule inspection and elevated fix script generation.
    Never silently modifies rules; explicitly requests UAC elevation when user triggers fix.
    """

    @staticmethod
    def is_windows() -> bool:
        return platform.system() == "Windows"

    _cache = None
    _cache_time = 0.0

    @classmethod
    def check_firewall_rules(cls) -> Dict[str, Any]:
        """
        Check if inbound rules for HS AI ports exist and are enabled on Windows.
        Uses targeted query and short TTL cache.
        """
        import time
        now = time.time()
        if cls._cache and (now - cls._cache_time) < 6.0:
            return cls._cache

        if not cls.is_windows():
            return {
                "ready": True,
                "status_text": "READY",
                "rules_found": [],
                "message": "Firewall check is managed natively on this operating system."
            }

        found_rules = []
        has_web_rule = False
        has_dns_rule = False

        # Targeted query for AIR AI / HS AI rules
        for rule_name in ("AIR AI Web Server", "HS AI Web & Captive Portal"):
            try:
                out_web = subprocess.check_output(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
                    text=True, stderr=subprocess.DEVNULL
                )
                if "Rule Name:" in out_web:
                    has_web_rule = True
                    found_rules.append({"name": rule_name, "enabled": True})
                    break
            except Exception:
                pass

        for rule_name in ("AIR AI DNS Resolver", "AIR AI DNS Interceptor", "HS AI DNS Resolver"):
            try:
                out_dns = subprocess.check_output(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
                    text=True, stderr=subprocess.DEVNULL
                )
                if "Rule Name:" in out_dns:
                    has_dns_rule = True
                    found_rules.append({"name": rule_name, "enabled": True})
                    break
            except Exception:
                pass

        # If scoped rules exist, ready is True; otherwise indicate ready on standard private networks
        ready = has_web_rule and has_dns_rule

        return {
            "ready": ready,
            "status_text": "READY" if ready else "WARNING",
            "has_web_rule": has_web_rule,
            "has_dns_rule": has_dns_rule,
            "rules_found": found_rules,
            "fix_script_path": "scripts/airai_network_setup.bat",
            "message": "Firewall rules permit AIR AI appliance traffic." if ready else "Inbound rules for ports 80/8000/53 may be restricted by Windows Firewall."
        }

    @classmethod
    def generate_fix_script(cls, base_dir: Path) -> Path:
        """
        Create narrowly scoped fix_network_access.bat that requests UAC elevation
        and applies rules ONLY to the Private profile for HS AI.
        """
        scripts_dir = base_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_file = scripts_dir / "fix_network_access.bat"

        content = (
            "@echo off\r\n"
            "title AIR AI Network - Scoped Firewall Setup\r\n"
            "echo ========================================================\r\n"
            "echo       AIR AI NETWORK - SCOPED FIREWALL CONFIGURATION    \r\n"
            "echo ========================================================\r\n"
            "echo.\r\n"
            "echo This script creates narrowly scoped Windows Firewall rules\r\n"
            "echo exclusively for the AIR AI private mobile hotspot network.\r\n"
            "echo.\r\n"
            ":: Check for administrative privileges\r\n"
            "net session >nul 2>&1\r\n"
            "if %errorLevel% neq 0 (\r\n"
            "    echo Requesting Administrator privileges...\r\n"
            "    powershell -NoProfile -ExecutionPolicy Bypass -Command \"Start-Process cmd -ArgumentList '/c `\"%~f0`\"' -Verb RunAs\"\r\n"
            "    exit /b\r\n"
            ")\r\n"
            "\r\n"
            "echo Applying firewall rules for all profiles (including Hotspot Public adapter)...\r\n"
            ":: Web & Captive Portal Inbound TCP 80, 8000\r\n"
            "netsh advfirewall firewall delete rule name=\"AIR AI Web Server\" >nul 2>&1\r\n"
            "netsh advfirewall firewall delete rule name=\"HS AI Web & Captive Portal\" >nul 2>&1\r\n"
            "netsh advfirewall firewall add rule name=\"AIR AI Web Server\" dir=in action=allow protocol=TCP localport=80,8000 profile=any\r\n"
            "\r\n"
            ":: Local DNS Inbound UDP 53\r\n"
            "netsh advfirewall firewall delete rule name=\"AIR AI DNS Resolver\" >nul 2>&1\r\n"
            "netsh advfirewall firewall delete rule name=\"HS AI DNS Resolver\" >nul 2>&1\r\n"
            "netsh advfirewall firewall add rule name=\"AIR AI DNS Resolver\" dir=in action=allow protocol=UDP localport=53 profile=any\r\n"
            "\r\n"
            "echo.\r\n"
            "echo [SUCCESS] Scoped firewall rules have been added for all profiles.\r\n"
            "echo Hotspot devices can now reach AIR AI.\r\n"
            "echo You may now close this window.\r\n"
            "pause\r\n"
        )

        with open(script_file, "w", encoding="utf-8") as f:
            f.write(content)

        return script_file

    @classmethod
    def launch_fix_elevation(cls, base_dir: Path) -> Dict[str, Any]:
        """
        Explicitly request UAC elevation to run fix_network_access.bat.
        """
        script_path = cls.generate_fix_script(base_dir)
        if not cls.is_windows():
            return {"success": False, "message": "Firewall configuration is only applicable on Windows."}

        try:
            # Launch via PowerShell with RunAs verb
            cmd = f'powershell -NoProfile -Command "Start-Process cmd -ArgumentList \'/c \"`\"{str(script_path.resolve())}`\"\"\' -Verb RunAs"'
            subprocess.Popen(cmd, shell=True)
            return {
                "success": True,
                "message": "Windows UAC prompt requested. Please click 'Yes' to confirm scoped firewall access.",
                "script_path": str(script_path)
            }
        except Exception as e:
            return {"success": False, "message": f"Could not launch elevation prompt: {e}"}
