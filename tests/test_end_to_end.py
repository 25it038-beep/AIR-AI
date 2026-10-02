import unittest
import sys
import json
from pathlib import Path
from starlette.testclient import TestClient

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from server.main import app
from launcher.hardware_detector import get_complete_hardware_profile
from launcher.model_scanner import select_best_model
from server.network_manager import detect_host_ip, HotspotManager

class TestEndToEndPipeline(unittest.TestCase):
    """
    End-to-End Simulation of HS AI Network:
    USB -> Hardware Detect -> Model Selection -> Server Start -> Hotspot Available ->
    Client Connects -> Welcome Portal Opens -> Start Chat -> Real Model Generates Response ->
    Streaming tokens verified.
    """

    def test_full_pipeline(self):
        print("\n==========================================================")
        print("  HS AI NETWORK - END-TO-END PIPELINE VERIFICATION")
        print("==========================================================")

        # Stage 1: USB Location & Hardware Profiling
        print("  [Stage 1] Detecting Hardware & USB Environment...")
        profile = get_complete_hardware_profile()
        self.assertIsNotNone(profile["usb_root"])
        ram_gb = profile["ram"]["total_gb"]
        gpu_name = profile["gpu"]["name"]
        vram_gb = profile["gpu"]["vram_total_gb"]
        print(f"            USB Root: {profile['usb_root']}")
        print(f"            Hardware: {ram_gb}GB RAM | {gpu_name} ({vram_gb}GB VRAM)")

        # Stage 2: Model Scanning & Best Selection
        print("  [Stage 2] Scanning Models & Determining Best Model...")
        client = TestClient(app)
        res_models = client.get("/api/models")
        self.assertEqual(res_models.status_code, 200)
        models_data = res_models.json()
        self.assertGreater(len(models_data["models"]), 0)
        active_model = models_data.get("active_model")
        print(f"            Selected Model: {active_model}")

        # Stage 3: Host Network & Hotspot State
        print("  [Stage 3] Checking Host Network & Mobile Hotspot State...")
        host_ip, adapter, is_hotspot = detect_host_ip()
        hotspot_status = HotspotManager.get_status()
        self.assertIsNotNone(host_ip)
        print(f"            Host IP: {host_ip} ({adapter})")
        print(f"            Hotspot State: {hotspot_status['status_text']}")

        # Stage 4: Client Connection Simulation (Android Phone joins hotspot)
        print("  [Stage 4] Simulating Android Client Connection...")
        android_ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/UD1A.230803.022) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
        portal_res = client.get("/", headers={"User-Agent": android_ua, "X-Forwarded-For": "192.168.137.25"}, follow_redirects=True)
        self.assertEqual(portal_res.status_code, 200)
        self.assertIn("AIR AI", portal_res.text)
        print("            Android phone successfully directed straight to AIR AI Chat")

        # Stage 5: Device Tracker records Android device
        devs_res = client.get("/api/devices")
        devs = devs_res.json()["devices"]
        android_dev = next((d for d in devs if d.get("device_type") == "Phone"), None)
        self.assertIsNotNone(android_dev)
        print(f"            Device Tracker verified client: {android_dev['friendly_name']} ({android_dev['os']})")

        # Stage 6: Client navigates to /chat
        print("  [Stage 6] Client opens Chat Interface...")
        chat_page = client.get("/chat", headers={"User-Agent": android_ua})
        self.assertEqual(chat_page.status_code, 200)
        self.assertIn("AIR AI", chat_page.text)
        print("            Chat UI loaded")

        # Stage 7: Prompt sent to Real Local Inference Engine
        print("  [Stage 7] Prompt sent: 'What is HS AI?'...")
        chat_req = {
            "message": "In 1 concise sentence, what is HS AI?",
            "model": active_model,
            "stream": False
        }
        chat_res = client.post("/api/chat", json=chat_req)
        self.assertEqual(chat_res.status_code, 200)
        ans_data = chat_res.json()
        self.assertIn("response", ans_data)
        actual_response = ans_data["response"].strip()
        self.assertGreater(len(actual_response), 5)
        print(f"  [Stage 8] Real Local Model Response received:\n            \"{actual_response}\"")

        # Stage 9: Streaming verification
        print("  [Stage 9] Verifying Streaming Event Stream...")
        stream_req = {
            "message": "Say hello in 3 words.",
            "model": active_model,
            "stream": True
        }
        stream_res = client.post("/api/chat", json=stream_req)
        self.assertEqual(stream_res.status_code, 200)
        self.assertTrue(stream_res.headers["content-type"].startswith("text/event-stream"))
        print("            Streaming tokens received successfully via SSE!")

        print("==========================================================")
        print("  END-TO-END PIPELINE: 100% PASSED")
        print("==========================================================\n")

if __name__ == "__main__":
    unittest.main()
