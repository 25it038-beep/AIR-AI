import unittest
import sys
import time
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from server.security import RateLimiter, Firewall, AuthManager, sanitize_filename, is_allowed_file

class TestSecurity(unittest.TestCase):
    def test_rate_limiter(self):
        limiter = RateLimiter(requests_per_minute=5)
        client_ip = "192.168.137.99"
        
        # 5 requests should pass
        for _ in range(5):
            self.assertTrue(limiter.is_allowed(client_ip))
            
        # 6th should be rejected
        self.assertFalse(limiter.is_allowed(client_ip))
        
        # Loopback is exempt
        for _ in range(10):
            self.assertTrue(limiter.is_allowed("127.0.0.1"))

    def test_firewall(self):
        fw = Firewall(max_clients=2)
        ip1 = "192.168.137.10"
        ip2 = "192.168.137.20"
        ip3 = "192.168.137.30"

        self.assertTrue(fw.can_connect(ip1))
        self.assertTrue(fw.can_connect(ip2))
        # 3rd should fail max clients
        self.assertFalse(fw.can_connect(ip3))

        # Block test
        fw.block_ip(ip1)
        self.assertTrue(fw.is_blocked(ip1))
        self.assertFalse(fw.can_connect(ip1))

    def test_auth_manager(self):
        auth = AuthManager(require_pin=True, network_pin="9999")
        self.assertTrue(auth.verify_pin("9999"))
        self.assertFalse(auth.verify_pin("1234"))

        token = auth.create_session("192.168.137.50")
        self.assertTrue(auth.is_valid_session(token, "192.168.137.50"))
        self.assertFalse(auth.is_valid_session("invalid_token", "192.168.137.50"))

    def test_sanitizer(self):
        self.assertEqual(sanitize_filename("../../etc/passwd"), "passwd")
        self.assertEqual(sanitize_filename("valid_image.png"), "valid_image.png")
        self.assertTrue(is_allowed_file("test.png"))
        self.assertTrue(is_allowed_file("code.py"))
        self.assertFalse(is_allowed_file("script.exe"))
        self.assertFalse(is_allowed_file("malicious.bat"))

if __name__ == "__main__":
    unittest.main()
