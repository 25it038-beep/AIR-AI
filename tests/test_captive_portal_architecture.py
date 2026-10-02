import os
import sys
import time
import socket
import unittest
import urllib.request
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from network.hotspot_detector import HotspotDetector
from network.dns_server import DNSServer
from network.captive_portal import CaptivePortalServer
from network.connectivity_check import ConnectivityCheckManager
from network.device_detector import DeviceDetector
from network.port_manager import PortManager
from network.firewall_checker import FirewallChecker

class TestCaptivePortalArchitecture(unittest.TestCase):

    def setUp(self):
        self.host_ip, self.adapter, self.is_hotspot = HotspotDetector.detect_host_ip()

    def test_01_hotspot_detector_ip(self):
        """Test host IP detection and virtual adapter filtering."""
        ip, adapter, is_hotspot = HotspotDetector.detect_host_ip()
        self.assertIsNotNone(ip)
        self.assertNotEqual(ip, "127.0.0.1")
        self.assertFalse(ip.startswith("169.254."))
        self.assertFalse(ip.startswith("192.168.56."), "VirtualBox adapter should be filtered out")
        print(f"  [+] Detected Host IP: {ip} via {adapter} (is_hotspot: {is_hotspot})")

        status = HotspotDetector.get_status()
        self.assertIn("status_text", status)
        self.assertIn("all_adapters", status)

    def test_02_dns_server_rfc1035_resolution(self):
        """Test RFC 1035 UDP 53 DNS server query response."""
        # Use unprivileged port for isolated test
        test_dns = DNSServer(host_ip="192.168.137.1", port=5355, listen_ip="127.0.0.1")
        started = test_dns.start()
        self.assertTrue(started, "DNS server should start")
        time.sleep(0.1)

        try:
            # Query for connectivitycheck.gstatic.com
            txn = b"\xaa\xbb"
            flags = b"\x01\x00"
            counts = b"\x00\x01\x00\x00\x00\x00\x00\x00"
            qname = b"\x11connectivitycheck\x07gstatic\x03com\x00"
            qtype_class = b"\x00\x01\x00\x01" # Type A, Class IN
            query = txn + flags + counts + qname + qtype_class

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2.0)
            sock.sendto(query, ("127.0.0.1", 5355))
            data, _ = sock.recvfrom(512)
            sock.close()

            # Verify resolved IP in answer
            resolved_ip = ".".join(str(b) for b in data[-4:])
            self.assertEqual(resolved_ip, "192.168.137.1")
            print("  [+] DNS resolved connectivitycheck.gstatic.com -> 192.168.137.1")
        finally:
            test_dns.stop()
            self.assertFalse(test_dns.is_running)

    def test_03_captive_portal_server_port_80(self):
        """Test dedicated CaptivePortalServer responding to probe URLs."""
        detector = DeviceDetector()
        portal = CaptivePortalServer(
            host_ip="192.168.137.1",
            port=8088, # Use isolated test port
            api_port=8000,
            base_dir=BASE_DIR,
            device_detector=detector
        )
        started = portal.start()
        self.assertTrue(started, "Captive portal server should start")
        time.sleep(0.1)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirect)

        try:
            # Test Android probe /generate_204
            try:
                opener.open("http://127.0.0.1:8088/generate_204", timeout=2.0)
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 302)
                loc = e.headers.get("Location", "")
                self.assertTrue(any(target in loc for target in ("/welcome", "/chat")))
                print(f"  [+] Android probe /generate_204 -> HTTP 302 to {loc}")

            # Test Realme/ColorOS probe /generate204 (no underscore)
            try:
                opener.open("http://127.0.0.1:8088/generate204", timeout=2.0)
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 302)
                loc = e.headers.get("Location", "")
                self.assertTrue(any(target in loc for target in ("/welcome", "/chat")))
                print(f"  [+] Realme probe /generate204 -> HTTP 302 to {loc}")

            # Test direct root / serves HTML (status 200)
            with urllib.request.urlopen("http://127.0.0.1:8088/", timeout=2.0) as res:
                self.assertEqual(res.status, 200)
                root_html = res.read().decode("utf-8")
                self.assertIn("AIR AI", root_html)
                print("  [+] Root / directly serves AIR AI (HTTP 200)")

            # Test Apple probe /hotspot-detect.html
            try:
                opener.open("http://127.0.0.1:8088/hotspot-detect.html", timeout=2.0)
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 302)
                loc = e.headers.get("Location", "")
                self.assertTrue(any(target in loc for target in ("/welcome", "/chat")))
                print(f"  [+] Apple CNA probe /hotspot-detect.html -> HTTP 302 to {loc}")

            # Test Windows probe /ncsi.txt
            try:
                opener.open("http://127.0.0.1:8088/ncsi.txt", timeout=2.0)
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 302)
                loc = e.headers.get("Location", "")
                self.assertTrue(any(target in loc for target in ("/welcome", "/chat")))
                print(f"  [+] Windows NCSI probe /ncsi.txt -> HTTP 302 to {loc}")

            # Test /connectivity-check JSON
            with urllib.request.urlopen("http://127.0.0.1:8088/connectivity-check", timeout=2.0) as res:
                self.assertEqual(res.status, 200)
                body = json.loads(res.read())
                self.assertEqual(body.get("status"), "captive_portal_active")
                print("  [+] /connectivity-check JSON response verified")

            # Test /welcome page serving
            with urllib.request.urlopen("http://127.0.0.1:8088/welcome", timeout=2.0) as res:
                self.assertEqual(res.status, 200)
                html = res.read().decode("utf-8")
                self.assertIn("AIR AI NETWORK", html)
                print("  [+] /welcome serves HTML Welcome Portal")

        finally:
            portal.stop()
            self.assertFalse(portal.is_running)

    def test_04_device_detector_captive_state(self):
        """Test device classification and captive portal served state."""
        detector = DeviceDetector()
        
        # Simulate Android phone hit
        ua_android = "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36"
        dev = detector.register_or_update("192.168.137.25", ua_android)
        self.assertEqual(dev["device_type"], "Phone")
        self.assertEqual(dev["os"], "Android")
        self.assertFalse(dev["captive_portal_served"])

        # Record captive hit
        detector.record_captive_hit("192.168.137.25", "/generate_204", ua_android)
        devices = detector.list_devices()
        dev_entry = next((d for d in devices if d["ip"] == "192.168.137.25"), None)
        self.assertIsNotNone(dev_entry)
        self.assertTrue(dev_entry["captive_portal_served"])
        self.assertEqual(dev_entry["last_probe_endpoint"], "/generate_204")
        print("  [+] Device detector correctly classified Android Phone & recorded captive portal served")

    def test_05_firewall_and_port_manager(self):
        """Test port checking and firewall fix script generation."""
        port_status = PortManager.get_ports_status(web_port=8000, captive_port=80, dns_port=53)
        self.assertIn("captive_portal_port_80", port_status)
        self.assertIn("dns_port_53", port_status)
        print(f"  [+] Port 80 Available: {port_status['captive_portal_port_80']['available']}")
        print(f"  [+] Port 53 Available: {port_status['dns_port_53']['available']}")

        script_path = FirewallChecker.generate_fix_script(BASE_DIR)
        self.assertTrue(script_path.exists())
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("netsh advfirewall firewall add rule", content)
        self.assertTrue("profile=any" in content or "profile=private" in content)
        print("  [+] Scoped firewall elevation script verified at scripts/fix_network_access.bat")

if __name__ == "__main__":
    unittest.main(verbosity=2)
