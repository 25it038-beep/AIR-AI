import asyncio
import time
from typing import AsyncGenerator

class ModelRequestQueue:
    """Manages concurrent client requests and tracks live inference metrics."""

    def __init__(self, max_concurrency: int = 3):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.max_concurrency = max_concurrency
        self.active_requests: int = 0
        self.total_processed: int = 0
        self.queued_requests: int = 0
        
        # Token speed tracking
        self.recent_tokens: int = 0
        self.recent_start_time: float = time.time()
        self.tokens_per_second: float = 0.0

    async def acquire(self):
        self.queued_requests += 1
        await self.semaphore.acquire()
        self.queued_requests = max(0, self.queued_requests - 1)
        self.active_requests += 1

    def release(self):
        self.active_requests = max(0, self.active_requests - 1)
        self.total_processed += 1
        self.semaphore.release()

    def record_token(self):
        now = time.time()
        self.recent_tokens += 1
        elapsed = now - self.recent_start_time
        if elapsed >= 2.0:
            self.tokens_per_second = round(self.recent_tokens / elapsed, 1)
            self.recent_tokens = 0
            self.recent_start_time = now

    def get_stats(self):
        now = time.time()
        elapsed = now - self.recent_start_time
        if elapsed > 4.0 and self.active_requests == 0:
            self.tokens_per_second = 0.0
        return {
            "active_requests": self.active_requests,
            "queued_requests": self.queued_requests,
            "max_concurrency": self.max_concurrency,
            "total_processed": self.total_processed,
            "tokens_per_second": self.tokens_per_second
        }
