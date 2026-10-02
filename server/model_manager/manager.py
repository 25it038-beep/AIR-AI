import os
import json
import glob
from pathlib import Path
from typing import Dict, List, Optional, Any
from .adapters.base import BaseModelEngine
from .adapters.ollama_adapter import OllamaAdapter
from .adapters.llama_cpp_adapter import LlamaCppAdapter
from .request_queue import ModelRequestQueue

class ModelManager:
    """Modular Model Manager for discovering, verifying, loading, and switching local AI models."""

    def __init__(self, models_root: str, config: Dict[str, Any]):
        self.models_root = Path(models_root)
        self.config = config
        self.registry_file = self.models_root / "registry.json"
        
        # Adapters
        ollama_url = config.get("model", {}).get("ollama_host", "http://127.0.0.1:11434")
        llama_cpp_url = config.get("model", {}).get("llama_server_host", "http://127.0.0.1:8080")
        
        self.adapters: Dict[str, BaseModelEngine] = {
            "ollama": OllamaAdapter(ollama_url),
            "llama_cpp": LlamaCppAdapter(llama_cpp_url)
        }
        self.active_engine_name = "ollama"
        self.active_model_id: Optional[str] = config.get("model", {}).get("active_model", "llama3.2:latest")
        self.active_model_info: Optional[Dict[str, Any]] = None
        
        # State
        self.is_loaded: bool = False
        self.loading_status: str = "Idle"
        self.loading_progress: int = 0
        self.last_error: Optional[str] = None
        
        # Concurrency & Request Queue
        max_concurrency = config.get("model", {}).get("max_concurrency", 3)
        self.queue = ModelRequestQueue(max_concurrency=max_concurrency)

    @property
    def current_adapter(self) -> BaseModelEngine:
        return self.adapters.get(self.active_engine_name, self.adapters["ollama"])

    def scan_models_directory(self) -> List[Dict[str, Any]]:
        """Scan models/text, vision, embedding, speech directories for GGUF/bin models."""
        discovered = []
        categories = ["text", "vision", "embedding", "speech"]

        for cat in categories:
            cat_dir = self.models_root / cat
            if not cat_dir.exists():
                continue
            
            # Find all .gguf files
            for file_path in cat_dir.glob("**/*.gguf"):
                size_bytes = file_path.stat().st_size
                size_gb = round(size_bytes / (1024**3), 2)
                model_name = file_path.stem
                discovered.append({
                    "id": f"local:{cat}/{file_path.name}",
                    "name": model_name,
                    "type": cat,
                    "format": "GGUF",
                    "file_path": str(file_path),
                    "size": f"{size_gb} GB",
                    "size_bytes": size_bytes,
                    "parameters": "Unknown",
                    "capabilities": [cat]
                })

        return discovered

    def load_registry(self) -> List[Dict[str, Any]]:
        """Load curated models from registry.json."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("models", [])
            except Exception:
                pass
        return []

    async def list_all_models(self) -> List[Dict[str, Any]]:
        """Aggregate models from registry, directory scan, and active backend."""
        registry = {m["id"]: m for m in self.load_registry()}
        dir_models = self.scan_models_directory()
        for m in dir_models:
            registry[m["id"]] = m

        # Query backend engine (e.g. Ollama)
        backend_models = []
        try:
            if await self.current_adapter.is_available():
                backend_models = await self.current_adapter.list_available_models()
        except Exception:
            pass

        # Merge
        result = []
        for b in backend_models:
            b_id = b["id"]
            if b_id in registry:
                merged = dict(registry[b_id])
                merged["installed"] = True
                merged["source"] = "runtime"
                result.append(merged)
            else:
                b["installed"] = True
                b["source"] = "runtime"
                result.append(b)

        # Add models found in registry/directory not yet registered in backend
        registered_ids = {r["id"] for r in result}
        for m_id, m in registry.items():
            if m_id not in registered_ids:
                m_copy = dict(m)
                m_copy["installed"] = ("file_path" in m_copy)
                m_copy["source"] = "local_drive"
                result.append(m_copy)

        return result

    def check_compatibility(self, model: Dict[str, Any], ram_gb: float, vram_gb: float) -> Dict[str, Any]:
        """Verify if model fits within host RAM/VRAM constraints."""
        req_ram = model.get("recommended_min_ram_gb", 4)
        req_vram = model.get("recommended_min_vram_gb", 0)

        can_run = True
        warnings = []

        if ram_gb < req_ram:
            can_run = False
            warnings.append(f"Requires {req_ram}GB RAM (Host has {ram_gb}GB)")

        if vram_gb < req_vram:
            warnings.append(f"VRAM ({vram_gb}GB) below recommended {req_vram}GB - will offload layers to CPU RAM")

        return {
            "compatible": can_run,
            "can_accelerate_gpu": vram_gb >= req_vram and vram_gb > 0,
            "warnings": warnings
        }

    async def load_model(self, model_id: str) -> bool:
        """Load and warm up model."""
        self.loading_status = f"Loading {model_id}..."
        self.loading_progress = 10
        self.last_error = None

        try:
            # Check if engine is alive
            if not await self.current_adapter.is_available():
                self.is_loaded = False
                self.loading_status = "AI MODEL OFFLINE"
                self.last_error = "Inference runtime engine is not responding."
                return False

            self.loading_progress = 40
            success = await self.current_adapter.load_model(model_id)
            if success:
                self.active_model_id = model_id
                self.is_loaded = True
                self.loading_status = "Running"
                self.loading_progress = 100
                
                # Fetch details
                models = await self.list_all_models()
                for m in models:
                    if m["id"] == model_id:
                        self.active_model_info = m
                        break
                return True
            else:
                self.is_loaded = False
                self.loading_status = "Failed to load model"
                self.last_error = f"Engine could not load {model_id}"
                return False
        except Exception as e:
            self.is_loaded = False
            self.loading_status = "Error loading model"
            self.last_error = str(e)
            return False

    async def unload_model(self) -> bool:
        """Unload active model."""
        if not self.active_model_id:
            return True
        success = await self.current_adapter.unload_model(self.active_model_id)
        if success:
            self.is_loaded = False
            self.loading_status = "Unloaded"
            self.loading_progress = 0
        return success

    async def get_status(self) -> Dict[str, Any]:
        """Report genuine model and engine status."""
        engine_online = False
        try:
            engine_online = await self.current_adapter.is_available()
        except Exception:
            pass

        return {
            "engine_online": engine_online,
            "engine_type": self.active_engine_name,
            "active_model": self.active_model_id if self.is_loaded else None,
            "is_loaded": self.is_loaded and engine_online,
            "status_text": ("Running" if self.is_loaded and engine_online else ("Engine Offline" if not engine_online else "Standby")),
            "loading_status": self.loading_status,
            "loading_progress": self.loading_progress,
            "last_error": self.last_error,
            "model_info": self.active_model_info,
            "queue_stats": self.queue.get_stats()
        }
