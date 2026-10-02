import sys
import time

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

def render_init_box():
    box = f"""
{CYAN}+--------------------------------------------------------+
|                        {BOLD}AIR AI{RESET}{CYAN}                          |
|                                                        |
|                 {BOLD}LOCAL AI. ANY DEVICE.{RESET}{CYAN}                  |
|                                                        |
|                    {YELLOW}Initializing...{RESET}{CYAN}                     |
|                                                        |
|   [1/4] Detecting hardware                             |
|   [2/4] Detecting models                               |
|   [3/4] Starting AI engine                             |
|   [4/4] Preparing local network                        |
+--------------------------------------------------------+{RESET}
"""
    try:
        print(box)
    except Exception:
        print("\n=== AIR AI Network: Local AI Initializing ===\n")

def print_step(step_num: int, label: str, detail: str = ""):
    try:
        sys.stdout.write(f"  {CYAN}> [{step_num}/4]{RESET} {label} {DIM}{detail}{RESET}\n")
        sys.stdout.flush()
    except Exception:
        print(f"  > [{step_num}/4] {label} {detail}")

def render_ready_summary(
    model_name: str,
    model_status: str,
    hotspot_status: str,
    hotspot_ip: str,
    host_port: int,
    connected_clients: int,
    drive_letter: str
):
    dot = "*"
    summary = f"""
{GREEN}{BOLD}==========================================================
                      AIR AI READY
=========================================================={RESET}

  {BOLD}AI Model:{RESET}
  {GREEN}{dot}{RESET} {model_name} ({model_status})

  {BOLD}Local Network:{RESET}
  {GREEN}{dot}{RESET} http://{hotspot_ip}:{host_port}
  {GREEN}{dot}{RESET} http://air-ai.local:{host_port}

  {BOLD}Hotspot:{RESET}
  {GREEN if hotspot_status == "ONLINE" else YELLOW}{dot}{RESET} {hotspot_status}

  {BOLD}Connected Devices:{RESET}
  {CYAN}{connected_clients}{RESET} connected

  {BOLD}USB Drive Location:{RESET}
  {DIM}{drive_letter}{RESET}

----------------------------------------------------------
  {BOLD}[ Welcome Portal ]{RESET}    http://{hotspot_ip}:{host_port}/
  {BOLD}[ Chat Interface ]{RESET}    http://{hotspot_ip}:{host_port}/chat
  {BOLD}[ Host Dashboard ]{RESET}    http://{hotspot_ip}:{host_port}/dashboard
  {BOLD}[ HS Solution    ]{RESET}    https://hs-ai-studio.onrender.com/
==========================================================
"""
    try:
        print(summary)
    except Exception:
        print(f"\nAIR AI READY: http://{hotspot_ip}:{host_port}/\n")
