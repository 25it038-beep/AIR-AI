import platform
import os
import sys
import ctypes
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List

def detect_usb_root() -> Path:
    """Dynamically determine the USB root folder without hardcoded paths."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller executable
        exe_path = Path(sys.executable).resolve()
        return exe_path.parent
    else:
        # Running as python script
        script_dir = Path(__file__).resolve().parent.parent
        return script_dir

def get_windows_version() -> Dict[str, str]:
    """Detect Windows edition, release, and build number."""
    plat = platform.system()
    if plat != "Windows":
        return {"os": plat, "version": platform.release(), "build": platform.version()}

    edition = "Windows"
    try:
        cmd = "powershell -NoProfile -Command \"(Get-CimInstance Win32_OperatingSystem).Caption\""
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        if out:
            edition = out
    except Exception:
        edition = f"Windows {platform.release()}"

    return {
        "os": edition,
        "version": platform.release(),
        "release": platform.release(),
        "build": platform.version(),
        "arch": platform.machine()
    }

def get_cpu_info() -> Dict[str, Any]:
    """Detect CPU model and core counts."""
    name = platform.processor() or "Generic Processor"
    cores = os.cpu_count() or 4
    plat = platform.system()

    if plat == "Windows":
        try:
            cmd = "powershell -NoProfile -Command \"(Get-CimInstance Win32_Processor).Name\""
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                name = out
        except Exception:
            pass

    return {
        "name": name,
        "logical_cores": cores
    }

def get_ram_info() -> Dict[str, Any]:
    """Detect total and available physical RAM in GB."""
    total_gb = 8.0
    avail_gb = 4.0
    percent_used = 50.0

    try:
        import psutil
        vm = psutil.virtual_memory()
        total_gb = round(vm.total / (1024**3), 2)
        avail_gb = round(vm.available / (1024**3), 2)
        percent_used = vm.percent
        return {"total_gb": total_gb, "available_gb": avail_gb, "percent_used": percent_used}
    except Exception:
        pass

    # Windows ctypes fallback
    if platform.system() == "Windows":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            msx = MEMORYSTATUSEX()
            msx.dwLength = ctypes.sizeof(msx)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(msx))
            total_gb = round(msx.ullTotalPhys / (1024**3), 2)
            avail_gb = round(msx.ullAvailPhys / (1024**3), 2)
            percent_used = float(msx.dwMemoryLoad)
        except Exception:
            pass

    return {"total_gb": total_gb, "available_gb": avail_gb, "percent_used": percent_used}

_gpu_cache = None
_gpu_cache_time = 0.0

def get_gpu_info() -> Dict[str, Any]:
    """Detect dedicated/integrated GPU and VRAM in GB with caching."""
    global _gpu_cache, _gpu_cache_time
    import time
    now = time.time()
    if _gpu_cache and (now - _gpu_cache_time) < 3.0:
        return _gpu_cache

    gpu_name = "Integrated Graphics"
    total_vram_gb = 0.0
    avail_vram_gb = 0.0
    has_cuda = False

    # Check nvidia-smi first for accurate discrete GPU metrics
    if shutil.which("nvidia-smi"):
        try:
            cmd = "nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits"
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            lines = out.splitlines()
            if lines:
                parts = [p.strip() for p in lines[0].split(",")]
                if len(parts) >= 3:
                    gpu_name = parts[0]
                    total_vram_gb = round(float(parts[1]) / 1024.0, 2)
                    avail_vram_gb = round(float(parts[2]) / 1024.0, 2)
                    has_cuda = True
                    _gpu_cache = {
                        "name": gpu_name,
                        "vram_total_gb": total_vram_gb,
                        "vram_available_gb": avail_vram_gb,
                        "has_cuda": has_cuda
                    }
                    _gpu_cache_time = now
                    return _gpu_cache
        except Exception:
            pass

    # Windows WMI fallback
    if platform.system() == "Windows":
        try:
            cmd = "powershell -NoProfile -Command \"Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM\""
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            lines = out.splitlines()[2:]
            for line in lines:
                parts = line.strip().rsplit(None, 1)
                if len(parts) == 2:
                    name, ram_bytes = parts
                    if "nvidia" in name.lower() or "amd" in name.lower() or "geforce" in name.lower() or "rtx" in name.lower():
                        gpu_name = name
                        try:
                            # 32-bit AdapterRAM cap fallback
                            b = int(ram_bytes)
                            total_vram_gb = round(b / (1024**3), 2)
                        except Exception:
                            pass
                        break
        except Exception:
            pass

    _gpu_cache = {
        "name": gpu_name,
        "vram_total_gb": total_vram_gb,
        "vram_available_gb": avail_vram_gb,
        "has_cuda": has_cuda
    }
    _gpu_cache_time = now
    return _gpu_cache

def get_complete_hardware_profile() -> Dict[str, Any]:
    """Compile comprehensive hardware snapshot."""
    usb_root = detect_usb_root()
    win_info = get_windows_version()
    cpu = get_cpu_info()
    ram = get_ram_info()
    gpu = get_gpu_info()

    return {
        "usb_root": str(usb_root),
        "drive_letter": str(usb_root.drive) if hasattr(usb_root, "drive") else "Local",
        "windows": win_info,
        "cpu": cpu,
        "ram": ram,
        "gpu": gpu
    }
