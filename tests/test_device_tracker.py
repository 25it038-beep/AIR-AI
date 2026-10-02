import unittest
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from server.device_manager.device_tracker import DeviceTracker

class TestDeviceTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = DeviceTracker(data_file=None)

    def test_user_agent_classification(self):
        android_ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
        parsed = self.tracker.parse_user_agent(android_ua)
        self.assertEqual(parsed["device_type"], "Phone")
        self.assertEqual(parsed["os"], "Android")

        iphone_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
        parsed_ios = self.tracker.parse_user_agent(iphone_ua)
        self.assertEqual(parsed_ios["device_type"], "Phone")
        self.assertEqual(parsed_ios["os"], "iOS")

        tablet_ua = "Mozilla/5.0 (Linux; Android 13; SM-X900) AppleWebKit/537.36"
        parsed_tab = self.tracker.parse_user_agent(tablet_ua)
        self.assertEqual(parsed_tab["device_type"], "Tablet")

        win_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        parsed_win = self.tracker.parse_user_agent(win_ua)
        self.assertEqual(parsed_win["device_type"], "Laptop / PC")
        self.assertEqual(parsed_win["os"], "Windows")

    def test_device_registration_and_blocking(self):
        dev = self.tracker.register_or_update("192.168.137.25", "Mozilla/5.0 (Linux; Android 14; Pixel 8)")
        self.assertEqual(dev["ip"], "192.168.137.25")
        self.assertFalse(dev["is_blocked"])

        devices = self.tracker.list_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["status"], "Active")

        # Test block
        self.tracker.block_device("192.168.137.25")
        self.assertTrue(self.tracker.is_blocked("192.168.137.25"))

        # Test unblock
        self.tracker.unblock_device("192.168.137.25")
        self.assertFalse(self.tracker.is_blocked("192.168.137.25"))

if __name__ == "__main__":
    unittest.main()
