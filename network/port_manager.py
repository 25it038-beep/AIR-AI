import socket
from typing import Dict, Any

class PortManager:
    """
    Checks and monitors availability of essential ports required for
    Captive Portal (TCP 80), Local DNS (UDP 53), and Web/WebSocket API (TCP 8000).
    """

    @staticmethod
    def test_port(port: int, proto: str = "tcp", bind_ip: str = "0.0.0.0") -> Dict[str, Any]:
        """
        Check if a given port can be bound.
        """
        sock_type = socket.SOCK_STREAM if proto.lower() == "tcp" else socket.SOCK_DGRAM
        s = socket.socket(socket.AF_INET, sock_type)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((bind_ip, port))
            s.close()
            return {
                "port": port,
                "proto": proto.upper(),
                "available": True,
                "status": "Available",
                "conflict": False,
                "message": f"{proto.upper()} port {port} is open and ready."
            }
        except OSError as e:
            return {
                "port": port,
                "proto": proto.upper(),
                "available": False,
                "status": "In Use / Conflict",
                "conflict": True,
                "error_code": getattr(e, "winerror", e.errno),
                "message": f"{proto.upper()} port {port} is currently occupied ({e})."
            }
        except Exception as e:
            return {
                "port": port,
                "proto": proto.upper(),
                "available": False,
                "status": "Error",
                "conflict": True,
                "message": str(e)
            }

    @classmethod
    def get_ports_status(cls, web_port: int = 8000, captive_port: int = 80, dns_port: int = 53) -> Dict[str, Any]:
        """
        Gather complete port audit for HS AI Network appliance.
        """
        c_80 = cls.test_port(captive_port, "tcp")
        w_8000 = cls.test_port(web_port, "tcp")
        d_53 = cls.test_port(dns_port, "udp")

        # If a port is occupied by our own active process, that's normal for active state
        return {
            "captive_portal_port_80": c_80,
            "web_api_port": w_8000,
            "dns_port_53": d_53,
            "has_conflict": any(p["conflict"] and p["port"] not in (web_port, captive_port) for p in (c_80, w_8000, d_53))
        }
