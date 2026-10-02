import urllib.request
import urllib.parse
from typing import Dict, Any, List

class ConnectivityCheckManager:
    """
    Manages OS-specific captive portal connectivity check probes and verification.
    Supports Android, Apple iOS/macOS, Windows, and Linux detection workflows.
    """

    PROBE_ENDPOINTS = [
        {"path": "/generate_204", "os": "Android / ChromeOS", "expected_action": "Redirect to /welcome (Trigger Captive Notification)"},
        {"path": "/gen_204", "os": "Android / ChromeOS", "expected_action": "Redirect to /welcome"},
        {"path": "/hotspot-detect.html", "os": "Apple iOS / macOS", "expected_action": "Redirect/Serve Welcome (Trigger Apple CNA)"},
        {"path": "/library/test/success.html", "os": "Apple CNA Fallback", "expected_action": "Redirect/Serve Welcome"},
        {"path": "/connecttest.txt", "os": "Windows 10/11 NCSI", "expected_action": "Redirect to /welcome (Trigger Windows Action prompt)"},
        {"path": "/ncsi.txt", "os": "Windows NCSI", "expected_action": "Redirect to /welcome"},
        {"path": "/canonical.html", "os": "Firefox / Linux", "expected_action": "Redirect to /welcome"},
        {"path": "/check_network_status.txt", "os": "Samsung Mobile", "expected_action": "Redirect to /welcome"},
        {"path": "/connectivity-check", "os": "Diagnostic / Generic", "expected_action": "JSON Status Response"}
    ]

    @classmethod
    def get_probe_list(cls) -> List[Dict[str, str]]:
        return cls.PROBE_ENDPOINTS

    @classmethod
    def test_local_probes(cls, base_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        """
        Run internal simulation against local captive portal endpoints and return real test results.
        """
        results = []
        all_passed = True

        test_paths = [
            "/generate_204",
            "/hotspot-detect.html",
            "/connecttest.txt",
            "/ncsi.txt",
            "/connectivity-check"
        ]

        # Use an opener that does NOT automatically follow redirects so we can verify the 302/307 status
        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirectHandler)

        for path in test_paths:
            url = f"{base_url.rstrip('/')}{path}"
            req = urllib.request.Request(url, headers={"User-Agent": "HS-AI-Diagnostic-Agent/1.0"})
            test_entry = {
                "endpoint": path,
                "url": url,
                "status_code": 0,
                "passed": False,
                "behavior": "",
                "target_location": None
            }

            try:
                with opener.open(req, timeout=2.5) as res:
                    test_entry["status_code"] = res.status
                    test_entry["passed"] = (res.status in (200, 302, 307))
                    test_entry["behavior"] = f"Responded with HTTP {res.status}"
            except urllib.error.HTTPError as e:
                test_entry["status_code"] = e.code
                loc = e.headers.get("Location")
                test_entry["target_location"] = loc
                if e.code in (302, 307):
                    test_entry["passed"] = True
                    test_entry["behavior"] = f"Correctly issued HTTP {e.code} redirect to {loc}"
                elif e.code == 200:
                    test_entry["passed"] = True
                    test_entry["behavior"] = "Served captive portal page"
                else:
                    test_entry["passed"] = False
                    test_entry["behavior"] = f"Unexpected HTTP status {e.code}"
                    all_passed = False
            except Exception as e:
                test_entry["passed"] = False
                test_entry["behavior"] = f"Connection error: {e}"
                all_passed = False

            results.append(test_entry)

        return {
            "all_passed": all_passed,
            "probes_tested": len(results),
            "results": results
        }
