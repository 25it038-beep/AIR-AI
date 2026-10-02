import os
import sys
import time
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
        client_ip = client_addr[0]
        backend_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            backend_sock.connect(("127.0.0.1", self.api_port))
        except Exception as e:
            logger.debug(f"Failed to connect to backend on port {self.api_port}: {e}")
            try:
                client_sock.close()
            except Exception:
                pass
            return

        # Pre-read initial packet to inject X-Forwarded-For header
        initial_client_data = b""
        try:
            client_sock.settimeout(2.0)
            initial_client_data = client_sock.recv(8192)
            client_sock.settimeout(None)
        except Exception:
            pass

        if initial_client_data:
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
