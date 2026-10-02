from .captive_portal import router as captive_router
from .status import router as status_router
from .models import router as models_router
from .devices import router as devices_router
from .network import router as network_router
from .chat import router as chat_router
from .security_api import router as security_router
from .files import router as files_router

__all__ = [
    "captive_router",
    "status_router",
    "models_router",
    "devices_router",
    "network_router",
    "chat_router",
    "security_router",
    "files_router"
]
