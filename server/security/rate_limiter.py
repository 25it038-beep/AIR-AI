import time
import threading
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("hs_ai.security.rate_limiter")

class RateLimiter:
    """
    Granular Multi-Bucket Sliding-Window Rate Limiter.
    Enforces independent, configurable request thresholds for:
      - 'auth': PIN and session authentication attempts (default: 5/min)
      - 'chat': AI prompt and inference requests (default: 20/min)
      - 'websocket': New WebSocket connection attempts (default: 10/min)
      - 'file_upload': Attachment and file uploads (default: 10/min)
      - 'api': General REST endpoints (default: 60/min)
    """

    DEFAULT_LIMITS: Dict[str, int] = {
        "auth": 5,
        "chat": 20,
        "websocket": 10,
        "file_upload": 10,
        "api": 60
    }

    def __init__(
        self,
        limits: Optional[Dict[str, int]] = None,
        window_seconds: float = 60.0,
        requests_per_minute: Optional[int] = None
    ):
        self.limits = dict(self.DEFAULT_LIMITS)
        if limits:
            self.limits.update(limits)
        if requests_per_minute:
            self.limits["api"] = requests_per_minute
        self.window_seconds = window_seconds

        # Map: bucket_name -> client_ip -> list of timestamps
        self.buckets: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        self.lock = threading.Lock()

    def set_limit(self, bucket: str, limit: int):
        """Configure the rate limit for a specific bucket."""
        with self.lock:
            self.limits[bucket] = max(1, limit)
            logger.info(f"Rate limit for bucket '{bucket}' set to {limit} req/{self.window_seconds}s")

    def is_allowed(self, client_ip: str, bucket: str = "api") -> bool:
        """
        Check if request from client_ip is allowed in the specified bucket.
        Loopback address (127.0.0.1, ::1) is exempt from rate limiting.
        """
        allowed, _ = self.check_rate_limit(client_ip, bucket)
        return allowed

    def check_rate_limit(self, client_ip: str, bucket: str = "api") -> Tuple[bool, int]:
        """
        Check rate limit and return (allowed: bool, retry_after_seconds: int).
        """
        if not client_ip or client_ip in ("127.0.0.1", "localhost", "::1"):
            return True, 0

        max_allowed = self.limits.get(bucket, self.limits["api"])
        now = time.time()
        window_start = now - self.window_seconds

        with self.lock:
            ip_times = self.buckets[bucket][client_ip]
            # Prune timestamps outside current sliding window
            valid_times = [t for t in ip_times if t > window_start]

            if len(valid_times) >= max_allowed:
                self.buckets[bucket][client_ip] = valid_times
                oldest = valid_times[0]
                retry_after = max(1, int(oldest + self.window_seconds - now))
                logger.warning(
                    f"Rate limit exceeded for {client_ip} on bucket '{bucket}' "
                    f"({len(valid_times)}/{max_allowed} in {self.window_seconds}s). Retry after {retry_after}s"
                )
                return False, retry_after

            valid_times.append(now)
            self.buckets[bucket][client_ip] = valid_times
            return True, 0

    def reset_client(self, client_ip: str, bucket: Optional[str] = None):
        """Reset rate limit history for a specific client IP."""
        with self.lock:
            if bucket:
                if bucket in self.buckets and client_ip in self.buckets[bucket]:
                    del self.buckets[bucket][client_ip]
            else:
                for b in self.buckets.values():
                    if client_ip in b:
                        del b[client_ip]

    def get_stats(self) -> Dict[str, Any]:
        """Return rate limiter overview for host dashboard."""
        with self.lock:
            active_ips = set()
            for b in self.buckets.values():
                active_ips.update(b.keys())
            return {
                "limits": dict(self.limits),
                "window_seconds": self.window_seconds,
                "monitored_clients_count": len(active_ips)
            }
