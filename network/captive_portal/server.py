import os
import sys
import re
import time
import json
import socket
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any

from .detector import ClientDetector

logger = logging.getLogger("hs_ai.captive_portal.server")

class DedicatedCaptivePortalServer:
    """
    Dedicated Port 80 Captive Portal Server for the HS AI Network.
    Binds to 0.0.0.0:80.
    Transparently proxies HTTP, SSE, and WebSockets to FastAPI (port 8000),
    while injecting real client IP in X-Forwarded-For so the backend and
    device tracker know the exact phone/tablet identity.
    """

    def __init__(self, host_ip: str = "192.168.137.1", port: int = 80, api_port: int = 8000,
                 detector: Optional[Any] = None, device_detector: Optional[Any] = None,
                 base_dir: Optional[Any] = None, **kwargs):
        self.host_ip = host_ip
        self.port = port
        self.api_port = api_port
        self.detector = detector or device_detector
        self.base_dir = base_dir
        self.server_sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.error_message: Optional[str] = None
        self.connections_handled = 0
        self._lock = threading.Lock()

    def update_host_ip(self, new_ip: str):
        self.host_ip = new_ip

    def start(self) -> bool:
        """Start the Port 80 Captive Portal Server in a background thread."""
        if self.is_running:
            return True

        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(("0.0.0.0", self.port))
            self.server_sock.listen(128)
            self.is_running = True
            self.error_message = None

            self.thread = threading.Thread(target=self._accept_loop, name="HSAI-CaptivePortal-80", daemon=True)
            self.thread.start()
            logger.info(f"Dedicated Captive Portal Server active on Port {self.port} (Proxying to 127.0.0.1:{self.api_port})")
            return True
        except OSError as e:
            self.is_running = False
            self.error_message = f"Port {self.port} occupied or unavailable ({e})"
            logger.warning(f"Could not bind Captive Portal on Port {self.port}: {e}")
            return False
        except Exception as e:
            self.is_running = False
            self.error_message = str(e)
            logger.error(f"Captive Portal server start failed: {e}")
            return False

    def stop(self):
        """Stop the Captive Portal server."""
        self.is_running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None
        logger.info("Captive Portal server stopped.")

    def _accept_loop(self):
        while self.is_running and self.server_sock:
            try:
                client_sock, client_addr = self.server_sock.accept()
                with self._lock:
                    self.connections_handled += 1
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, client_addr),
                    name=f"HSAI-CP-Client-{client_addr[0]}",
                    daemon=True
                ).start()
            except (socket.error, OSError):
                break
            except Exception as e:
                if not self.is_running:
                    break
                logger.debug(f"Proxy accept error: {e}")

    def _handle_client(self, client_sock: socket.socket, client_addr: tuple):
        # Pre-read initial packet to inspect request and inject X-Forwarded-For header
        initial_client_data = b""
        try:
            client_sock.settimeout(2.0)
            initial_client_data = client_sock.recv(8192)
            client_sock.settimeout(None)
        except Exception:
            pass

        if not initial_client_data:
            try:
                client_sock.close()
            except Exception:
                pass
            return

        # Fast-path for captive portal probes and external domain requests
        first_line = initial_client_data.split(b"\r\n")[0].decode("latin-1", errors="ignore")
        method, path = "", ""
        parts = first_line.split()
        if len(parts) >= 2:
            method, path = parts[0].upper(), parts[1]

        probe_paths = {
            "/generate_204", "/gen_204", "/generate204",
            "/hotspot-detect.html", "/hotspotdetect.html",
            "/connecttest.txt", "/msftconnecttest.txt", "/ncsi.txt",
            "/check_network_status.txt", "/library/test/success.html",
            "/mobile/status.php", "/wifi/status", "/ptlogin/status",
            "/canonical.html", "/success.txt"
        }

        # Determine actual local IP this client connected to
        target_ip = self.host_ip
        try:
            sock_ip = client_sock.getsockname()[0]
            if sock_ip and sock_ip not in ("0.0.0.0", "127.0.0.1"):
                target_ip = sock_ip
        except Exception:
            pass

        # Destination paths that must NEVER be redirected (prevent loops)
        NON_REDIRECT_PREFIXES = (
            "/chat", "/welcome", "/api", "/ws", "/assets", "/js", "/css",
            "/static", "/favicon.ico", "/sw.js", "/manifest.json"
        )
        is_dest_path = any(
            path == p or path.startswith(p + "/") or path.startswith(p + "?")
            for p in NON_REDIRECT_PREFIXES
        )

        # Check if user typed an external domain (e.g. google.com, apple.com)
        is_external_host = False
        if not is_dest_path:
            for line in initial_client_data.split(b"\r\n")[1:]:
                if line.lower().startswith(b"host:"):
                    host_val = line.split(b":", 1)[1].strip().decode("latin-1", errors="ignore").split(":")[0]
                    known_hosts = (
                        target_ip.lower(), self.host_ip.lower(), "127.0.0.1", "localhost",
                        "air-ai.local", "hs-ai.local", "air.ai", "hs.ai"
                    )
                    if host_val and host_val.lower() not in known_hosts:
                        # If it's a private network IP or loopback, don't treat it as external
                        is_private = host_val.startswith(("192.168.", "10.", "172.", "127.", "169.254."))
                        if not is_private:
                            is_external_host = True
                    break

        # 1. Direct fast-path for /connectivity-check
        if path == "/connectivity-check":
            data = json.dumps({"status": "captive_portal_active", "host_ip": target_ip}).encode()
            resp = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(data)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + data
            )
            try:
                client_sock.sendall(resp)
                try:
                    client_sock.shutdown(socket.SHUT_WR)
                except Exception:
                    pass
                client_sock.close()
            except Exception:
                pass
            return

        # 2. Direct fast-path for /welcome
        if path == "/welcome":
            portal_file = (Path(self.base_dir) / "frontend" / "portal.html") if self.base_dir else None
            content = portal_file.read_bytes() if (portal_file and portal_file.exists()) else b"<h1>AIR AI NETWORK</h1>"
            resp = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                b"Content-Length: " + str(len(content)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + content
            )
            try:
                client_sock.sendall(resp)
                try:
                    client_sock.shutdown(socket.SHUT_WR)
                except Exception:
                    pass
                client_sock.close()
            except Exception:
                pass
            return

        # 3. Captive portal probe redirect (ONLY for probes or external domains, NEVER for /chat)
        if not is_dest_path and (path in probe_paths or is_external_host):
            dest = f"http://{target_ip}/chat"
            html = (
                f'<!DOCTYPE html><html><head><meta charset="utf-8">'
                f'<meta http-equiv="refresh" content="0; url={dest}">'
                f'<script>window.location.replace("{dest}");</script></head>'
                f'<body style="font-family:sans-serif;background:#090d16;color:#e2e8f0;text-align:center;padding:2rem;">'
                f'<p>Connecting to AIR AI...</p><p><a href="{dest}" style="color:#2dd4bf;">Click here if not redirected</a></p></body></html>'
            )
            resp = (
                b"HTTP/1.1 302 Found\r\n"
                b"Location: " + dest.encode() + b"\r\n"
                b"Cache-Control: no-cache, no-store, must-revalidate, max-age=0\r\n"
                b"Pragma: no-cache\r\n"
                b"Expires: 0\r\n"
                b"Content-Type: text/html\r\n"
                b"Content-Length: " + str(len(html)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + html.encode()
            )
            try:
                client_sock.sendall(resp)
                try:
                    client_sock.shutdown(socket.SHUT_WR)
                except Exception:
                    pass
                client_sock.close()
            except Exception:
                pass
            return

        backend_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        backend_sock.settimeout(0.5)
        try:
            backend_sock.connect(("127.0.0.1", self.api_port))
            backend_sock.settimeout(None)
        except Exception as e:
            logger.debug(f"Failed to connect to backend on port {self.api_port}: {e}")
            try:
                # 1. Connectivity Check API
                if path == "/connectivity-check":
                    data = json.dumps({"status": "captive_portal_active", "host_ip": self.host_ip}).encode()
                    resp = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: application/json\r\n"
                        b"Content-Length: " + str(len(data)).encode() + b"\r\n"
                        b"Connection: close\r\n\r\n" + data
                    )
                    client_sock.sendall(resp)
                    try:
                        client_sock.shutdown(socket.SHUT_WR)
                    except Exception:
                        pass
                    client_sock.close()
                    return

                # 2. Welcome Portal Page
                if path == "/welcome":
                    portal_file = (Path(self.base_dir) / "frontend" / "portal.html") if self.base_dir else None
                    content = portal_file.read_bytes() if (portal_file and portal_file.exists()) else b"<h1>AIR AI NETWORK</h1>"
                    resp = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: text/html; charset=utf-8\r\n"
                        b"Content-Length: " + str(len(content)).encode() + b"\r\n"
                        b"Connection: close\r\n\r\n" + content
                    )
                    client_sock.sendall(resp)
                    try:
                        client_sock.shutdown(socket.SHUT_WR)
                    except Exception:
                        pass
                    client_sock.close()
                    return

                # 3. Chat / Root Page
                if path in ("/", "/chat"):
                    chat_file = (Path(self.base_dir) / "frontend" / "chat.html") if self.base_dir else None
                    content = chat_file.read_bytes() if (chat_file and chat_file.exists()) else b"<h1>AIR AI</h1>"
                    resp = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: text/html; charset=utf-8\r\n"
                        b"Content-Length: " + str(len(content)).encode() + b"\r\n"
                        b"Connection: close\r\n\r\n" + content
                    )
                    client_sock.sendall(resp)
                    try:
                        client_sock.shutdown(socket.SHUT_WR)
                    except Exception:
                        pass
                    client_sock.close()
                    return

                # 4. Fallback 302
                dest = f"http://{self.host_ip}/chat"
                client_sock.sendall(
                    f"HTTP/1.1 302 Found\r\nLocation: {dest}\r\nConnection: close\r\n\r\n".encode()
                )
                try:
                    client_sock.shutdown(socket.SHUT_WR)
                except Exception:
                    pass
                client_sock.close()
            except Exception:
                pass
            return

        # Check if this is an HTTP request and inject real client IP
        try:
            if b"\r\n\r\n" in initial_client_data:
                parts = initial_client_data.split(b"\r\n\r\n", 1)
                header_block = parts[0].decode("latin-1", errors="replace")
                body_rest = parts[1] if len(parts) > 1 else b""

                # Extract user-agent for client classification
                ua = ""
                for line in header_block.split("\r\n"):
                    if line.lower().startswith("user-agent:"):
                        ua = line.split(":", 1)[1].strip()
                        break

                if self.detector:
                    self.detector.register_or_update(client_ip, ua)

                # Inject X-Forwarded-For and X-Real-IP
                forwarded_header = f"\r\nX-Forwarded-For: {client_ip}\r\nX-Real-IP: {client_ip}\r\nX-Forwarded-Proto: http"
                new_header_block = header_block + forwarded_header
                initial_client_data = new_header_block.encode("latin-1") + b"\r\n\r\n" + body_rest
        except Exception:
            pass

        try:
            backend_sock.sendall(initial_client_data)
        except Exception:
            pass

        done_count = [2]
        lock = threading.Lock()
        done_event = threading.Event()

        def pipe(src: socket.socket, dst: socket.socket):
            try:
                while self.is_running:
                    data = src.recv(32768)
                    if not data:
                        break
                    dst.sendall(data)
            except Exception:
                pass
            finally:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except Exception:
                    pass
                with lock:
                    done_count[0] -= 1
                    if done_count[0] <= 0:
                        done_event.set()

        t1 = threading.Thread(target=pipe, args=(client_sock, backend_sock), daemon=True)
        t2 = threading.Thread(target=pipe, args=(backend_sock, client_sock), daemon=True)
        t1.start()
        t2.start()

        def cleanup():
            done_event.wait(timeout=300)
            try:
                client_sock.close()
            except Exception:
                pass
            try:
                backend_sock.close()
            except Exception:
                pass

        threading.Thread(target=cleanup, daemon=True).start()

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "status_text": "RUNNING" if self.is_running else "FAILED",
            "port": self.port,
            "api_port": self.api_port,
            "host_ip": self.host_ip,
            "connections_handled": self.connections_handled,
            "error": self.error_message
        }
