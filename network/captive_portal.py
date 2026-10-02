import os
import sys
import time
import socket
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any

from .device_detector import DeviceDetector

logger = logging.getLogger("hs_ai.captive_portal")

class CaptivePortalServer:
    """
    Dedicated local captive portal server manager running on Port 80.
    Uses high-performance transparent bidirectional TCP proxying to FastAPI (port 8000).
    Ensures that HTTP requests, Server-Sent Events (SSE), and WebSockets (/ws/chat)
    work natively on standard Port 80 without cross-port redirects, CORS issues,
    or WebSocket handshake failures.
    """

    def __init__(self, host_ip: str = "192.168.137.1", port: int = 80, api_port: int = 8000,
                 base_dir: Optional[Path] = None, device_detector: Optional[DeviceDetector] = None):
        self.host_ip = host_ip
        self.port = port
        self.api_port = api_port
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent
        self.frontend_dir = self.base_dir / "frontend"
        self.device_detector = device_detector
        self.server_sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.error_message: Optional[str] = None
        self.probes_served_count = 0

    def update_host_ip(self, new_ip: str):
        self.host_ip = new_ip

    def start(self) -> bool:
        """Start the Port 80 TCP proxy server in a daemon thread."""
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
            logger.info(f"Captive Portal Server active on Port {self.port} (Forwarding to 127.0.0.1:{self.api_port})")
            return True
        except OSError as e:
            self.is_running = False
            self.error_message = f"Port {self.port} occupied or unavailable: {e}"
            logger.warning(f"Could not bind Captive Portal on Port {self.port}: {e}")
            return False
        except Exception as e:
            self.is_running = False
            self.error_message = str(e)
            logger.error(f"Captive Portal start failed: {e}")
            return False

    def stop(self):
        """Stop the Captive Portal TCP server."""
        self.is_running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None
        logger.info("Captive Portal Server stopped.")

    def _accept_loop(self):
        """Accept incoming client connections on port 80 and forward to backend."""
        while self.is_running and self.server_sock:
            try:
                client_sock, client_addr = self.server_sock.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, client_addr),
                    name=f"HSAI-Proxy-{client_addr[0]}",
                    daemon=True
                ).start()
            except (socket.error, OSError):
                # Socket closed during shutdown
                break
            except Exception as e:
                if not self.is_running:
                    break
                logger.debug(f"Proxy accept error: {e}")

    def _handle_client(self, client_sock: socket.socket, client_addr: tuple):
        """Connect to FastAPI backend and pipe data bidirectionally with graceful half-close."""
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

        # Pre-read initial packet to inject X-Forwarded-For and X-Real-IP
        initial_client_data = b""
        client_ip = client_addr[0]
        try:
            client_sock.settimeout(2.0)
            initial_client_data = client_sock.recv(8192)
            client_sock.settimeout(None)
        except Exception:
            pass

        if initial_client_data:
            try:
                if b"\r\n\r\n" in initial_client_data:
                    parts = initial_client_data.split(b"\r\n\r\n", 1)
                    header_block = parts[0].decode("latin-1", errors="replace")
                    body_rest = parts[1] if len(parts) > 1 else b""

                    ua = ""
                    for line in header_block.split("\r\n"):
                        if line.lower().startswith("user-agent:"):
                            ua = line.split(":", 1)[1].strip()
                            break

                    if self.device_detector:
                        self.device_detector.register_or_update(client_ip, ua)

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
            "active": self.is_running,
            "port": self.port,
            "backend_port": self.api_port,
            "host_ip": self.host_ip,
            "error": self.error_message,
            "status_text": "ACTIVE" if self.is_running else "INACTIVE",
            "welcome_url": f"http://{self.host_ip}/welcome" if self.port == 80 else f"http://{self.host_ip}:{self.port}/welcome"
        }

class CaptivePortalHandler:
    """Backward compatibility placeholder for CaptivePortalHandler."""
    pass
