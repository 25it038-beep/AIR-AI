from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List
from ..model_manager.manager import ModelManager
from launcher.hardware_detector import get_ram_info, get_gpu_info
from .security_api import verify_host_admin

router = APIRouter(prefix="/api/models", tags=["Models"])

class LoadModelRequest(BaseModel):
    model_id: str

@router.get("")
async def list_models(request: Request):
    """List all available models with hardware compatibility."""
    model_mgr: ModelManager = request.app.state.model_manager
    ram = get_ram_info()
    gpu = get_gpu_info()
    
    models = await model_mgr.list_all_models()
    annotated = []
    for m in models:
        compat = model_mgr.check_compatibility(m, ram.get("total_gb", 8.0), gpu.get("vram_total_gb", 0.0))
        m_copy = dict(m)
        m_copy["compatible"] = compat["compatible"]
        m_copy["can_accelerate_gpu"] = compat["can_accelerate_gpu"]
        m_copy["warnings"] = compat["warnings"]
        m_copy["is_active"] = (m["id"] == model_mgr.active_model_id and model_mgr.is_loaded)
        annotated.append(m_copy)

    return {
        "models": annotated,
        "active_model": model_mgr.active_model_id,
        "is_loaded": model_mgr.is_loaded,
        "status": model_mgr.loading_status
    }

@router.post("/load")
async def load_model(payload: LoadModelRequest, request: Request, authorization: Optional[str] = Header(None)):
    """Switch and warm up selected model. Host administrator only."""
    verify_host_admin(request, authorization)
    model_mgr: ModelManager = request.app.state.model_manager
    success = await model_mgr.load_model(payload.model_id)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=model_mgr.last_error or f"Failed to load model {payload.model_id}"
        )
    return {
        "success": True,
        "model_id": payload.model_id,
        "status": "Running"
    }

@router.post("/unload")
async def unload_model(request: Request, authorization: Optional[str] = Header(None)):
    """Unload model from memory. Host administrator only."""
    verify_host_admin(request, authorization)
    model_mgr: ModelManager = request.app.state.model_manager
    success = await model_mgr.unload_model()
    return {"success": success, "status": "Unloaded"}

@router.get("/active")
async def active_model(request: Request):
    """Get active model details."""
    model_mgr: ModelManager = request.app.state.model_manager
    status = await model_mgr.get_status()
    return status
