import unittest
import sys
from pathlib import Path

# Add root directory to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from launcher.hardware_detector import (
    get_windows_version,
    get_cpu_info,
    get_ram_info,
    get_gpu_info,
    get_complete_hardware_profile
)

class TestHardwareDetector(unittest.TestCase):
    def test_windows_version(self):
        info = get_windows_version()
        self.assertIn("os", info)
        self.assertIn("version", info)
        print(f"  [OK] Detected OS: {info['os']} ({info['version']})")

    def test_cpu_detection(self):
        cpu = get_cpu_info()
        self.assertIn("name", cpu)
        self.assertGreater(cpu["logical_cores"], 0)
        print(f"  [OK] Detected CPU: {cpu['name']} ({cpu['logical_cores']} cores)")

    def test_ram_detection(self):
        ram = get_ram_info()
        self.assertGreater(ram["total_gb"], 0)
        self.assertGreaterEqual(ram["percent_used"], 0.0)
        print(f"  [OK] Detected RAM: {ram['total_gb']} GB total, {ram['available_gb']} GB avail ({ram['percent_used']}%)")

    def test_gpu_detection(self):
        gpu = get_gpu_info()
        self.assertIn("name", gpu)
        self.assertIn("vram_total_gb", gpu)
        print(f"  [OK] Detected GPU: {gpu['name']} ({gpu['vram_total_gb']} GB VRAM, CUDA={gpu['has_cuda']})")

    def test_complete_profile(self):
        profile = get_complete_hardware_profile()
        self.assertIn("usb_root", profile)
        self.assertIn("cpu", profile)
        self.assertIn("ram", profile)
        self.assertIn("gpu", profile)

if __name__ == "__main__":
    unittest.main()
