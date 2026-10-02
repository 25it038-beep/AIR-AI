import socket
import struct
import threading
import time

MDNS_ADDR = "224.0.0.251"
MDNS_PORT = 5353

class MDNSService:
    """Lightweight mDNS (multicast DNS) responder for 'hs-ai.local'."""

    def __init__(self, hostname: str = "hs-ai.local", host_ip: str = "127.0.0.1"):
        self.hostname = hostname.lower().rstrip(".")
        self.host_ip = host_ip
        self.running = False
        self.sock = None
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def update_ip(self, new_ip: str):
        self.host_ip = new_ip

    def _run(self):
        try:
            # Create UDP socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Bind to port 5353
            try:
                self.sock.bind(("", MDNS_PORT))
            except Exception:
                # If port 5353 is already taken by system mDNS / bonjour, bind to 0
                return

            # Join multicast group
            mreq = struct.pack("4sl", socket.inet_aton(MDNS_ADDR), socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.sock.settimeout(2.0)
        except Exception:
            return

        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                if not data or len(data) < 12:
                    continue
                # Check if the query matches any local hostnames
                query_lower = data.lower()
                matched_name = None
                for candidate in (b"hs-ai", b"hsai", b"ai.local", b"portal.local", b"hotspot.local"):
                    if candidate in query_lower:
                        matched_name = candidate.decode("ascii", errors="ignore")
                        break
                if matched_name:
                    self._send_response(addr, data, query_hostname=matched_name)
            except socket.timeout:
                continue
            except Exception:
                break

    def _send_response(self, addr, query_data, query_hostname: str = None):
        """Construct standard DNS A-record response."""
        try:
            tx_id = query_data[:2]
            flags = b"\x84\x00"  # Response, Authoritative
            qd_count = b"\x00\x00"
            an_count = b"\x00\x01"
            ns_count = b"\x00\x00"
            ar_count = b"\x00\x00"

            header = tx_id + flags + qd_count + an_count + ns_count + ar_count

            # Name: \x05hs-ai\x05local\x00
            target_host = query_hostname if query_hostname and "." in query_hostname else self.hostname
            name_parts = target_host.split(".")
            name_bytes = b"".join(bytes([len(p)]) + p.encode("ascii") for p in name_parts) + b"\x00"

            qtype = b"\x00\x01"  # A record
            qclass = b"\x80\x01"  # IN with flush cache bit
            ttl = struct.pack("!I", 120)  # 120 seconds TTL
            rdlength = struct.pack("!H", 4)
            rdata = socket.inet_aton(self.host_ip)

            answer = name_bytes + qtype + qclass + ttl + rdlength + rdata
            packet = header + answer

            # Send both to unicast querier and multicast
            self.sock.sendto(packet, (MDNS_ADDR, MDNS_PORT))
        except Exception:
            pass

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
