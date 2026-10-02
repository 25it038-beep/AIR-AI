import unittest
import sys
from pathlib import Path
from starlette.testclient import TestClient

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from server.main import app

class TestAPIEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_captive_portal_probes(self):
        # Android
        res_android = self.client.get("/generate_204", follow_redirects=False)
        self.assertEqual(res_android.status_code, 302)
        self.assertTrue(any(dest in res_android.headers.get("location", "") for dest in ("/welcome", "/chat", "/")))

        # Apple
        res_apple = self.client.get("/hotspot-detect.html", follow_redirects=False)
        self.assertEqual(res_apple.status_code, 302)

        # Windows
        res_win = self.client.get("/ncsi.txt", follow_redirects=False)
        self.assertEqual(res_win.status_code, 302)

    def test_health_check(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_stats_endpoint(self):
        res = self.client.get("/api/stats")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("cpu_percent", data)
        self.assertIn("ram_percent", data)
        self.assertIn("gpu_name", data)
        self.assertIn("vram_percent", data)

    def test_status_endpoint(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("network", data)
        self.assertIn("ai_engine", data)
        self.assertIn("model", data)
        self.assertIn("host", data)

    def test_dashboard_endpoint(self):
        res = self.client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("system", data)
        self.assertIn("ai_engine", data)
        self.assertIn("network", data)
        self.assertIn("qr_svg", data["network"])
        self.assertTrue(data["network"]["qr_svg"].startswith("<svg"))

    def test_models_list(self):
        res = self.client.get("/api/models")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("models", data)
        self.assertGreater(len(data["models"]), 0)

    def test_devices_list(self):
        res = self.client.get("/api/devices")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("devices", data)

    def test_chat_persistence(self):
        # Save a conversation
        test_chats = [{"id": "test_1", "title": "Test Chat", "messages": []}]
        res_post = self.client.post("/api/chats", json=test_chats)
        self.assertEqual(res_post.status_code, 200)

        # Retrieve
        res_get = self.client.get("/api/chats")
        self.assertEqual(res_get.status_code, 200)
        loaded = res_get.json()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["id"], "test_1")

if __name__ == "__main__":
    unittest.main()
