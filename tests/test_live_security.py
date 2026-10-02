import unittest
import urllib.request
import urllib.error
import json

class TestLiveSecurity(unittest.TestCase):
    """Live verification of the running HS AI Network security layer."""

    @classmethod
    def setUpClass(cls):
        # Check if server is running on localhost:8000
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2) as res:
                cls.server_available = (res.status == 200)
        except Exception:
            cls.server_available = False

    def setUp(self):
        if not self.server_available:
            self.skipTest("Live HS AI server not running on 127.0.0.1:8000")

    def test_01_directory_traversal_defense(self):
        boundary = "BoundaryTest12345"
        filename = "../../../../test_traversal.txt"
        body_str = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: text/plain\r\n\r\n"
            f"Secure payload\r\n"
            f"--{boundary}--\r\n"
        )
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/files/upload",
            data=body_str.encode("utf-8"),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req) as res:
            upload_res = json.loads(res.read().decode())
            sanitized_name = upload_res.get("filename")
            self.assertNotIn("/", sanitized_name)
            self.assertNotIn("\\", sanitized_name)
            self.assertTrue(sanitized_name.endswith("test_traversal.txt"))

    def test_02_pin_enforcement_and_untrusted_client_blocking(self):
        # Enable PIN
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/admin/pin/toggle",
            data=json.dumps({"require_pin": True}).encode(),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req)

        try:
            # Try unauthenticated chat as remote hotspot client (192.168.137.99)
            req_no_auth = urllib.request.Request(
                "http://127.0.0.1:8000/api/chat",
                data=json.dumps({
                    "model": "llama3.2:latest",
                    "messages": [{"role": "user", "content": "hello"}]
                }).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Forwarded-For": "192.168.137.99"
                }
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_no_auth)
            self.assertEqual(ctx.exception.code, 401)
        finally:
            # Always reset require_pin to False
            req_reset = urllib.request.Request(
                "http://127.0.0.1:8000/api/admin/pin/toggle",
                data=json.dumps({"require_pin": False}).encode(),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req_reset)

    def test_03_host_admin_endpoint_protection(self):
        req_admin_remote = urllib.request.Request(
            "http://127.0.0.1:8000/api/admin/pin",
            headers={"X-Forwarded-For": "192.168.137.99"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_admin_remote)
        self.assertEqual(ctx.exception.code, 403)

    def test_04_device_pin_authentication_and_chat(self):
        # Host retrieves current PIN
        pin_res = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/admin/pin").read().decode())
        current_pin = pin_res["current_pin"]

        # Remote device logs in with PIN
        login_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/auth/login",
            data=json.dumps({"pin": current_pin, "client_name": "Verified iPhone"}).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Forwarded-For": "192.168.137.99"
            }
        )
        with urllib.request.urlopen(login_req) as res:
            login_data = json.loads(res.read().decode())
            self.assertTrue(login_data.get("success"))
            session_token = login_data["token"]

        # Remote device chats with session token
        auth_chat_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/chat",
            data=json.dumps({
                "model": "llama3.2:latest",
                "messages": [{"role": "user", "content": "Say hello"}],
                "stream": False
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {session_token}",
                "X-Forwarded-For": "192.168.137.99"
            }
        )
        with urllib.request.urlopen(auth_chat_req) as res:
            chat_out = json.loads(res.read().decode())
            self.assertIn("response", chat_out)
            self.assertTrue(len(chat_out["response"]) > 0)

if __name__ == "__main__":
    unittest.main()
