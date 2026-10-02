import socket
import threading
import struct
import logging
import subprocess
from typing import Optional, Tuple, Set, Dict, Any

logger = logging.getLogger("hs_ai.captive_portal.dns")


class CaptiveDNSManager:
    """
    AIR AI Captive Portal DNS Interceptor.
    
    Listens on both UDP port 5353 (portproxy target) and attempts UDP 53.
    Resolves ALL domains to the hotspot IP to force captive portal detection.
    
    Windows ICS Architecture:
    - ICS/SharedAccess PID binds 0.0.0.0:53 (UDP)
    - netsh portproxy adds a TCP intercept for 192.168.137.1:53 → 127.0.0.1:5353
    - Our server listens on 0.0.0.0:5353 (UDP) — receives portproxied DNS queries
    - Additionally tries 0.0.0.0:53 (UDP) — may co-exist with ICS on some configs
    
    For captive portal: resolve EVERY domain to host_ip so phone's OS gets:
    - connectivitycheck.gstatic.com → 192.168.137.1 (HTTP 302 → captive portal!)
    - captive.apple.com → 192.168.137.1 (HTTP 302 → Apple CNA opens!)
    - msftconnecttest.com → 192.168.137.1 (HTTP 302 → Windows notification!)
    """

    def __init__(self, host_ip: str = "192.168.137.1", port: int = 53, listen_ip: str = "0.0.0.0"):
        self.host_ip = host_ip
        self.port = port
        self.listen_ip = listen_ip
        self.alt_port = 5353  # portproxy target port

        self._socks: list = []
        self._threads: list = []
        self.is_running = False
        self.is_intercepting_verified = False
        self.fallback_mode = False
        self.status_message = "Initializing"
        self.queries_answered = 0
        self._lock = threading.Lock()

    def update_host_ip(self, new_ip: str):
        with self._lock:
            self.host_ip = new_ip

    def start(self) -> bool:
        """Start DNS servers on port 53 and port 5353 (portproxy target)."""
        if self.is_running:
            return True

        bound_any = False

        # Attempt port 53 (may co-exist with ICS on some Windows configs)
        sock53 = self._try_bind_udp(self.listen_ip, 53)
        if sock53:
            bound_any = True
            self._socks.append(sock53)
            t = threading.Thread(target=self._serve_loop, args=(sock53,), name="AIRAI-DNS-53", daemon=True)
            t.start()
            self._threads.append(t)
            logger.info("AIR AI DNS: Bound to UDP 0.0.0.0:53")

        # Always bind port 5353 (portproxy target — avoids ICS conflict)
        sock5353 = self._try_bind_udp(self.listen_ip, self.alt_port)
        if sock5353:
            bound_any = True
            self._socks.append(sock5353)
            t = threading.Thread(target=self._serve_loop, args=(sock5353,), name="AIRAI-DNS-5353", daemon=True)
            t.start()
            self._threads.append(t)
            logger.info("AIR AI DNS: Bound to UDP 0.0.0.0:5353 (portproxy target)")

        # Also bind on the hotspot IP directly
        sock_hotspot = self._try_bind_udp(self.host_ip, self.alt_port)
        if sock_hotspot:
            bound_any = True
            self._socks.append(sock_hotspot)
            t = threading.Thread(target=self._serve_loop, args=(sock_hotspot,), name="AIRAI-DNS-HS", daemon=True)
            t.start()
            self._threads.append(t)
            logger.info(f"AIR AI DNS: Bound to UDP {self.host_ip}:5353")

        if bound_any:
            self.is_running = True
            self.fallback_mode = not sock53  # fallback if we couldn't get port 53
            self.is_intercepting_verified = bool(sock53)
            if self.fallback_mode:
                self.status_message = f"Running on port 5353 (portproxy target — Windows ICS owns port 53)"
            else:
                self.status_message = f"RUNNING on ports 53 + 5353 → resolving all domains to {self.host_ip}"
            logger.info(f"AIR AI DNS Manager: {self.status_message}")
            return True
        else:
            self.is_running = False
            self.fallback_mode = True
            self.status_message = "Could not bind DNS on any port"
            logger.warning("AIR AI DNS: Could not bind any DNS port")
            return False

    def _try_bind_udp(self, ip: str, port: int) -> Optional[socket.socket]:
        """Attempt to bind a UDP socket. Return socket or None on failure."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(2.0)
            s.bind((ip, port))
            s.settimeout(None)
            return s
        except OSError as e:
            logger.debug(f"DNS bind {ip}:{port} failed: {e}")
            return None
        except Exception as e:
            logger.debug(f"DNS bind {ip}:{port} error: {e}")
            return None

    def stop(self):
        self.is_running = False
        for s in self._socks:
            try:
                s.close()
            except Exception:
                pass
        self._socks.clear()
        self._threads.clear()
        logger.info("AIR AI DNS Manager stopped.")

    def _serve_loop(self, sock: socket.socket):
        while self.is_running:
            try:
                data, client_addr = sock.recvfrom(512)
                if not data or len(data) < 12:
                    continue
                response = self._build_response(data)
                if response:
                    sock.sendto(response, client_addr)
                    with self._lock:
                        self.queries_answered += 1
                        self.is_intercepting_verified = True
            except (socket.error, OSError):
                break
            except Exception as e:
                logger.debug(f"DNS loop error: {e}")

    def _parse_query_domain(self, data: bytes) -> Tuple[str, int]:
        domain_parts = []
        idx = 12
        while idx < len(data):
            length = data[idx]
            if length == 0:
                idx += 1
                break
            if idx + 1 + length > len(data):
                return "", 0
            domain_parts.append(data[idx + 1:idx + 1 + length].decode("ascii", errors="ignore"))
            idx += 1 + length

        domain = ".".join(domain_parts).lower()
        qtype = 0
        if idx + 2 <= len(data):
            qtype = struct.unpack("!H", data[idx:idx + 2])[0]
        return domain, qtype

    def _build_response(self, query: bytes) -> Optional[bytes]:
        """Build DNS A-record response pointing ANY domain to our hotspot IP."""
        try:
            txn_id = query[:2]
            domain, qtype = self._parse_query_domain(query)

            # Log captive check domains at info level
            captive_keywords = ("connectivitycheck", "gstatic", "captive", "apple",
                                "ncsi", "msftconnect", "detectportal", "connectivity",
                                "samsung", "miui", "hicloud", "oppomobile", "coloros",
                                "vivo.com", "kindle-wifi", "allawnos", "heytap", "realme", "oneplus")
            if any(kw in domain for kw in captive_keywords):
                logger.info(f"[DNS CAPTIVE PROBE] {domain} → {self.host_ip}")

            # Resolve ALL domains to our captive portal IP
            # This is the correct captive portal behavior — any DNS query
            # from a connected phone should get our IP so the HTTP probe
            # hits our server and returns 302 to trigger the captive portal popup.
            ip_parts = [int(p) for p in self.host_ip.split(".")]
            ip_bytes = bytes(ip_parts)

            flags = b"\x81\x80"          # Standard response, no error
            qdcount = b"\x00\x01"
            ancount = b"\x00\x01"
            nscount = b"\x00\x00"
            arcount = b"\x00\x00"
            header = txn_id + flags + qdcount + ancount + nscount + arcount

            # Copy the question section
            idx = 12
            while idx < len(query) and query[idx] != 0:
                idx += 1 + query[idx]
            idx += 5  # skip null terminator + qtype + qclass
            question = query[12:idx]

            ans_ptr = b"\xc0\x0c"        # Pointer to question name
            ans_type = b"\x00\x01"       # Type A
            ans_class = b"\x00\x01"      # Class IN
            ans_ttl = struct.pack("!I", 10)  # 10 second TTL — low so cache doesn't persist
            ans_len = b"\x00\x04"
            ans_data = ip_bytes

            answer = ans_ptr + ans_type + ans_class + ans_ttl + ans_len + ans_data
            return header + question + answer
        except Exception as e:
            logger.debug(f"DNS response build error: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        ports = [53 if "DNS-53" in t.name else 5353 for t in self._threads if t.is_alive()]
        return {
            "running": self.is_running,
            "status_text": "RUNNING" if self.is_running else "NOT RUNNING",
            "verified_intercept": self.is_intercepting_verified,
            "fallback_mode": self.fallback_mode,
            "active_ports": ports,
            "host_ip": self.host_ip,
            "queries_answered": self.queries_answered,
            "message": self.status_message
        }
