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
        self.socks: list = []
        self.threads: list = []
        self.is_running = False
        self.error_message: Optional[str] = None
        self.queries_answered = 0
        self._lock = threading.Lock()

    def update_host_ip(self, new_ip: str):
        with self._lock:
            self.host_ip = new_ip

    def start(self) -> bool:
        """Start the DNS server across all relevant interfaces (Hotspot IP, localhost, wildcard)."""
        if self.is_running:
            return True

        self.socks = []
        self.threads = []
        target_set = []

        # If specific listen_ip is provided (e.g. tests or isolated loopback), bind only that
        if self.listen_ip and self.listen_ip != "0.0.0.0":
            target_set.append((self.listen_ip, self.port))
        else:
            # 1. Hotspot IP specifically (wins over 0.0.0.0 in Winsock)
            if self.host_ip and self.host_ip not in ("0.0.0.0", "127.0.0.1"):
                target_set.append((self.host_ip, self.port))
            # 2. Localhost
            target_set.append(("127.0.0.1", self.port))
            # 3. Wildcard listen_ip (0.0.0.0)
            target_set.append(("0.0.0.0", self.port))

            # Only bind port 5353 if standard DNS port 53 is being configured
            if self.port == 53:
                if self.host_ip and self.host_ip not in ("0.0.0.0", "127.0.0.1"):
                    target_set.append((self.host_ip, 5353))
                target_set.append(("127.0.0.1", 5353))
                target_set.append(("0.0.0.0", 5353))

        # Deduplicate while preserving order
        seen = set()
        targets = []
        for pair in target_set:
            if pair not in seen:
                seen.add(pair)
                targets.append(pair)

        self.is_running = True
        bound_any = False
        for ip, port in targets:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((ip, port))
                self.socks.append(s)
                t = threading.Thread(target=self._serve_loop, args=(s,), name=f"AIRAI-DNS-{ip}-{port}", daemon=True)
                t.start()
                self.threads.append(t)
                bound_any = True
                logger.info(f"Local DNS bound to {ip}:{port} (Resolving to {self.host_ip})")
            except Exception as e:
                logger.debug(f"DNS bind to {ip}:{port} skipped: {e}")

        if bound_any:
            self.error_message = None
            logger.info(f"AIR AI DNS active across {len(self.socks)} interface sockets.")
            return True
        else:
            self.is_running = False
            self.error_message = "Could not bind DNS on any interface"
            logger.warning("Could not bind DNS server on UDP ports.")
            return False

    def stop(self):
        """Safely stop all DNS server sockets."""
        self.is_running = False
        for s in self.socks:
            try:
                s.close()
            except Exception:
                pass
        self.socks.clear()
        self.threads.clear()
        logger.info("Local DNS server stopped.")

    def _serve_loop(self, sock: socket.socket):
        """Packet processing loop for a specific bound socket."""
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
            except (socket.error, OSError):
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
