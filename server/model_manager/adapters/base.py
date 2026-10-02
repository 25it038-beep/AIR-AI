from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, List, Optional, Any

class BaseModelEngine(ABC):
    """Abstract Base Class for local AI inference runtimes."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if runtime engine is running/available."""
        pass

    @abstractmethod
    async def list_available_models(self) -> List[Dict[str, Any]]:
        """List models installed and available in this engine."""
        pass

    @abstractmethod
    async def load_model(self, model_id: str) -> bool:
        """Preload or warm up a model."""
        pass

    @abstractmethod
    async def unload_model(self, model_id: str) -> bool:
        """Unload model from VRAM/RAM."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        images: Optional[List[str]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream generated tokens."""
        pass

    @abstractmethod
    async def chat_stream(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream conversational chat tokens."""
        pass
