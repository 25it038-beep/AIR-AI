import json
import urllib.request
import urllib.error
import asyncio
from typing import AsyncGenerator, Dict, List, Optional, Any
from .base import BaseModelEngine

class OllamaAdapter(BaseModelEngine):
    """Production adapter for local Ollama engine runtime."""

    def __init__(self, host: str = "http://127.0.0.1:11434"):
        self.host = host.rstrip("/")

    async def is_available(self) -> bool:
        """Check if Ollama is listening and responding."""
        loop = asyncio.get_event_loop()
        def _check():
            try:
                req = urllib.request.Request(f"{self.host}/api/tags")
                with urllib.request.urlopen(req, timeout=1.5) as res:
                    return res.status == 200
            except Exception:
                return False
        return await loop.run_in_executor(None, _check)

    async def list_available_models(self) -> List[Dict[str, Any]]:
        """Fetch list of local models."""
        loop = asyncio.get_event_loop()
        def _fetch():
            try:
                req = urllib.request.Request(f"{self.host}/api/tags")
                with urllib.request.urlopen(req, timeout=3.0) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    models = []
                    for m in data.get("models", []):
                        name = m.get("name", "")
                        details = m.get("details", {})
                        size_bytes = m.get("size", 0)
                        size_gb = round(size_bytes / (1024**3), 2)
                        family = details.get("family", "text")
                        models.append({
                            "id": name,
                            "name": name,
                            "size": f"{size_gb} GB",
                            "size_bytes": size_bytes,
                            "format": details.get("format", "GGUF"),
                            "parameters": details.get("parameter_size", "unknown"),
                            "family": family,
                            "type": "vision" if "vl" in name.lower() or "vision" in name.lower() else "text"
                        })
                    return models
            except Exception:
                return []
        return await loop.run_in_executor(None, _fetch)

    async def load_model(self, model_id: str) -> bool:
        """Warm up model in RAM/VRAM."""
        loop = asyncio.get_event_loop()
        def _load():
            try:
                payload = json.dumps({"model": model_id, "prompt": "", "stream": False, "keep_alive": "60m"}).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.host}/api/generate",
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=30.0) as res:
                    return res.status == 200
            except Exception:
                return False
        return await loop.run_in_executor(None, _load)

    async def unload_model(self, model_id: str) -> bool:
        """Unload model by setting keep_alive to 0."""
        loop = asyncio.get_event_loop()
        def _unload():
            try:
                payload = json.dumps({"model": model_id, "keep_alive": 0}).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.host}/api/generate",
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10.0) as res:
                    return res.status == 200
            except Exception:
                return False
        return await loop.run_in_executor(None, _unload)

    async def generate_stream(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        images: Optional[List[str]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream generation tokens."""
        payload = {
            "model": model_id,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature}
        }
        if system_prompt:
            payload["system"] = system_prompt
        if images:
            payload["images"] = images

        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _worker():
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.host}/api/generate",
                    data=data,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=180.0) as res:
                    for line in res:
                        if not line:
                            continue
                        line_str = line.decode("utf-8").strip()
                        if line_str:
                            try:
                                parsed = json.loads(line_str)
                                token = parsed.get("response", "")
                                is_done = parsed.get("done", False)
                                loop.call_soon_threadsafe(queue.put_nowait, (token, is_done, None))
                                if is_done:
                                    break
                            except Exception:
                                pass
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, ("", True, str(e)))

        threading_thread = asyncio.create_task(asyncio.to_thread(_worker))

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
        """Stream chat tokens."""
        opts = {"temperature": temperature}
        if options:
            opts.update(options)

        payload = {
            "model": model_id,
            "messages": messages,
            "stream": True,
            "options": opts
        }

        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _worker():
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.host}/api/chat",
                    data=data,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=180.0) as res:
                    for line in res:
                        if not line:
                            continue
                        line_str = line.decode("utf-8").strip()
                        if line_str:
                            try:
                                parsed = json.loads(line_str)
                                msg = parsed.get("message", {})
                                token = msg.get("content", "")
                                is_done = parsed.get("done", False)
                                loop.call_soon_threadsafe(queue.put_nowait, (token, is_done, None))
                                if is_done:
                                    break
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
