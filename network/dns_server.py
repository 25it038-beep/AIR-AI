import socket
import threading
import struct
import logging
from typing import Optional, Tuple, Set

logger = logging.getLogger("hs_ai.dns")

class DNSServer:
    """
    Dedicated Local DNS Component for the HS AI Network.
    Listens on UDP port 53.
    Resolves captive portal probe domains and local network requests to the HS AI Host IP.
    Safely stoppable and non-blocking.
    """

    CAPTIVE_DOMAINS: Set[str] = {
        # Android / Google / ChromeOS
        "connectivitycheck.gstatic.com",
        "connectivitycheck.android.com",
        "clients3.google.com",
        "play.googleapis.com",
        # Apple iOS / macOS
        "captive.apple.com",
        "www.apple.com",
        "www.airport.us",
        "www.ibook.info",
        "www.itools.info",
        "www.thinkdifferent.us",
        "apple.com",
        # Windows NCSI
        "msftconnecttest.com",
        "www.msftconnecttest.com",
        "www.msftncsi.com",
        "ipv6.msftncsi.com",
        # Firefox / Linux
        "detectportal.firefox.com",
        # Samsung
        "connectivity.samsung.com",
        # Realme / Oppo / OnePlus (ColorOS / AllawnOS)
        "conn-service-in-04.allawnos.com",
        "allawnos.com",
        "coloros.com",
        "oppomobile.com",
        "heytapmobile.com",
        # Xiaomi / MIUI
        "connect.rom.miui.com",
        "miui.com",
        "xiaomi.com",
        # Local Discovery
        "air-ai.local",
        "air.ai",
        "hs-ai.local",
        "hs-ai",
        "hsai.local",
        "portal.hs-ai"
    }

    def __init__(self, host_ip: str = "192.168.137.1", port: int = 53, listen_ip: str = "0.0.0.0", resolve_all_captive: bool = True):
        self.host_ip = host_ip
        self.port = port
        self.listen_ip = listen_ip
        self.resolve_all_captive = resolve_all_captive
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.error_message: Optional[str] = None
        self.queries_answered = 0
        self._lock = threading.Lock()

    def update_host_ip(self, new_ip: str):
        with self._lock:
            self.host_ip = new_ip

    def start(self) -> bool:
        """Start the DNS server in a background daemon thread."""
        if self.is_running:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.listen_ip, self.port))
            self.is_running = True
            self.error_message = None

            self.thread = threading.Thread(target=self._serve_loop, name="HSAI-DNS-Server", daemon=True)
            self.thread.start()
            logger.info(f"Local DNS server started on {self.listen_ip}:{self.port} (Resolving to {self.host_ip})")
            return True
        except Exception as e:
            self.is_running = False
            self.error_message = str(e)
            logger.warning(f"Could not bind DNS server on UDP port {self.port}: {e}")
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
            return False

    def stop(self):
        """Safely stop the DNS server."""
        self.is_running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        logger.info("Local DNS server stopped.")

    def _serve_loop(self):
        """Packet processing loop."""
        while self.is_running and self.sock:
            try:
                data, client_addr = self.sock.recvfrom(512)
                if not data or len(data) < 12:
                    continue

                response = self._build_response(data)
                if response:
                    self.sock.sendto(response, client_addr)
                    with self._lock:
                        self.queries_answered += 1
            except (socket.error, OSError):
                # Socket closed or interrupted during shutdown
                break
            except Exception as e:
                logger.debug(f"DNS loop error: {e}")

    def _parse_query_domain(self, data: bytes) -> Tuple[str, int]:
        """Extract domain name and question type from DNS query payload."""
        domain_parts = []
        idx = 12
        while idx < len(data):
            length = data[idx]
            if length == 0:
                idx += 1
                break
            # Guard against invalid pointers / corrupt packets
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
        """Build RFC 1035 DNS response with A-record pointing to HS AI Host IP."""
        try:
            # Header unpacking
            txn_id = query[:2]
            domain, qtype = self._parse_query_domain(query)

            # Check if domain matches captive detection or local names, or if resolve_all is active
            should_resolve = False
            if domain in self.CAPTIVE_DOMAINS or any(domain.endswith(cd) for cd in self.CAPTIVE_DOMAINS):
                should_resolve = True
            elif domain in ("hs-ai", "hs-ai.local", "hsai.local", "ai.local"):
                should_resolve = True
            elif self.resolve_all_captive and ("google" in domain or "apple" in domain or "microsoft" in domain or "ncsi" in domain or "check" in domain or "detect" in domain):
                should_resolve = True

            # If not resolving, send standard NXDOMAIN or forward (we send NXDOMAIN or ignore)
            if not should_resolve:
                # Still resolve A queries so captive redirection works universally on local hotspot
                should_resolve = True

            # Standard query response flags: 0x8180 (Response, Opcode 0, No Error)
            flags = b"\x81\x80"
            qdcount = b"\x00\x01"
            ancount = b"\x00\x01"  # 1 Answer
            nscount = b"\x00\x00"
            arcount = b"\x00\x00"

            header = txn_id + flags + qdcount + ancount + nscount + arcount

            # Find end of question section
            idx = 12
            while idx < len(query) and query[idx] != 0:
                idx += 1 + query[idx]
            idx += 5  # Null terminator + 2 bytes QTYPE + 2 bytes QCLASS
            question = query[12:idx]

            # Parse host IP to bytes
            ip_parts = [int(p) for p in self.host_ip.split(".")]
            ip_bytes = bytes(ip_parts)

            # Answer Section (RFC 1035)
            # Pointer to domain name in question section: 0xc00c
            ans_ptr = b"\xc0\x0c"
            ans_type = b"\x00\x01"   # Type A
            ans_class = b"\x00\x01"  # Class IN
            ans_ttl = struct.pack("!I", 60)  # TTL 60 seconds
            ans_len = b"\x00\x04"    # 4 bytes for IPv4
            ans_data = ip_bytes

            answer = ans_ptr + ans_type + ans_class + ans_ttl + ans_len + ans_data
            return header + question + answer
        except Exception as e:
            logger.debug(f"Failed to build DNS response: {e}")
            return None

    def get_status(self) -> dict:
        return {
            "active": self.is_running,
            "port": self.port,
            "host_ip": self.host_ip,
            "queries_answered": self.queries_answered,
            "error": self.error_message
        }
