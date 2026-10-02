import json
import urllib.request
import urllib.error
import asyncio
from typing import AsyncGenerator, Dict, List, Optional, Any
from .base import BaseModelEngine

class LlamaCppAdapter(BaseModelEngine):
    """Adapter for llama.cpp (llama-server) runtime."""

    def __init__(self, host: str = "http://127.0.0.1:8080"):
        self.host = host.rstrip("/")

    async def is_available(self) -> bool:
        loop = asyncio.get_event_loop()
        def _check():
            try:
                req = urllib.request.Request(f"{self.host}/health")
                with urllib.request.urlopen(req, timeout=1.5) as res:
                    return res.status == 200
            except Exception:
                return False
        return await loop.run_in_executor(None, _check)

    async def list_available_models(self) -> List[Dict[str, Any]]:
        # llama.cpp server typically serves one active model loaded into memory
        avail = await self.is_available()
        if avail:
            return [{
                "id": "llama-cpp-active",
                "name": "llama.cpp Active Model",
                "size": "N/A",
                "format": "GGUF",
                "type": "text"
            }]
        return []

    async def load_model(self, model_id: str) -> bool:
        return await self.is_available()

    async def unload_model(self, model_id: str) -> bool:
        return True

    async def generate_stream(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        images: Optional[List[str]] = None
    ) -> AsyncGenerator[str, None]:
        full_prompt = f"{system_prompt}\n{prompt}" if system_prompt else prompt
        payload = {
            "prompt": full_prompt,
            "temperature": temperature,
            "stream": True
        }
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _worker():
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.host}/completion",
                    data=data,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=120.0) as res:
                    for line in res:
                        if not line:
                            continue
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data: "):
                            raw = line_str[6:].strip()
                            if raw == "[DONE]":
                                loop.call_soon_threadsafe(queue.put_nowait, ("", True, None))
                                break
                            try:
                                parsed = json.loads(raw)
                                token = parsed.get("content", "")
                                loop.call_soon_threadsafe(queue.put_nowait, (token, False, None))
                            except Exception:
                                pass
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, ("", True, str(e)))

        asyncio.create_task(asyncio.to_thread(_worker))

        while True:
            token, is_done, err = await queue.get()
            if err:
                raise RuntimeError(err)
            if token:
                yield token
            if is_done:
                break

    async def chat_stream(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        # Format messages into conversation text or OpenAI format
        payload = {
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _worker():
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.host}/v1/chat/completions",
                    data=data,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=120.0) as res:
                    for line in res:
                        if not line:
                            continue
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data: "):
                            raw = line_str[6:].strip()
                            if raw == "[DONE]":
                                loop.call_soon_threadsafe(queue.put_nowait, ("", True, None))
                                break
                            try:
                                parsed = json.loads(raw)
                                choices = parsed.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    token = delta.get("content", "")
                                    loop.call_soon_threadsafe(queue.put_nowait, (token, False, None))
                            except Exception:
                                pass
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, ("", True, str(e)))

        asyncio.create_task(asyncio.to_thread(_worker))

        while True:
            token, is_done, err = await queue.get()
            if err:
                raise RuntimeError(err)
            if token:
                yield token
            if is_done:
                break
