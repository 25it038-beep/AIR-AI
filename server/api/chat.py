import os
import json
import time
import uuid
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from ..model_manager.manager import ModelManager
from ..security.auth import AuthManager
from ..security.rate_limiter import RateLimiter
from ..security.sanitizer import (
    validate_prompt,
    validate_conversation_id,
    validate_model_name
)
from ..web_search import WebSearchEngine
from .security_api import get_request_token

logger = logging.getLogger("hs_ai.chat")

router = APIRouter(prefix="/api", tags=["Chat"])

class ChatMessage(BaseModel):
    role: str
    content: str
    images: Optional[List[str]] = None

class ChatRequest(BaseModel):
    message: Optional[str] = None
    prompt: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None
    conversation_id: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = True
    images: Optional[List[str]] = None
    web_search: Optional[bool] = False

class TestInferenceRequest(BaseModel):
    prompt: Optional[str] = "Say hello"

@router.post("/chat")
async def chat_endpoint(payload: ChatRequest, request: Request, authorization: Optional[str] = Header(None)):
    """
    Core AI Chat Endpoint with Authentication, Granular Rate Limiting, and Input Validation.
    Connects to the real local inference engine with streaming SSE or JSON response.
    """
    model_mgr: ModelManager = request.app.state.model_manager
    auth_mgr: AuthManager = request.app.state.auth_manager
    rate_limiter: RateLimiter = request.app.state.rate_limiter

    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")

    # 1. Authentication check
    token = get_request_token(request, authorization)
    if auth_mgr.require_pin and not auth_mgr.is_valid_session(token, client_ip):
        logger.warning(f"Unauthenticated chat request from {client_ip}")
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please connect with the network PIN on the AIR AI portal."
        )

    # 2. Rate limiting (20 requests/minute per device)
    allowed, retry_after = rate_limiter.check_rate_limit(client_ip, "chat")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded (Chat limit: 20 req/min). Please wait {retry_after} seconds."
        )

    # 3. Input validation
    conv_id = payload.conversation_id or str(uuid.uuid4())[:8]
    valid_conv, conv_err = validate_conversation_id(conv_id)
    if not valid_conv:
        raise HTTPException(status_code=400, detail=conv_err)

    if payload.model:
        valid_model, model_err = validate_model_name(payload.model)
        if not valid_model:
            raise HTTPException(status_code=400, detail=model_err)

    # Build messages list
    messages = []
    if payload.messages:
        messages = payload.messages
        # Validate latest user message
        if messages and isinstance(messages[-1], dict) and "content" in messages[-1]:
            valid_p, p_err = validate_prompt(messages[-1]["content"])
            if not valid_p:
                raise HTTPException(status_code=400, detail=p_err)
    elif payload.message or payload.prompt:
        user_text = payload.message or payload.prompt
        valid_p, p_err = validate_prompt(user_text)
        if not valid_p:
            raise HTTPException(status_code=400, detail=p_err)
        msg_obj = {"role": "user", "content": user_text}
        if payload.images:
            msg_obj["images"] = payload.images
        messages = [msg_obj]
    else:
        raise HTTPException(status_code=400, detail="Missing message or prompt in request.")

    # Section 16: Structured server logging
    logger.info(f"[SERVER] Request received from {client_ip}")
    logger.info(f"[SERVER] Conversation: {conv_id}")

    # Real-Time Web Search & Temporal Context Injection
    search_data = None
    last_query = ""
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content"):
            last_query = m["content"]
            break

    should_search = payload.web_search or (last_query and WebSearchEngine.is_live_query(last_query))
    if should_search and last_query:
        try:
            search_data = WebSearchEngine.search(last_query, max_results=5)
            if search_data.get("success"):
                search_ctx = WebSearchEngine.format_search_context(search_data)
                messages.insert(0, {"role": "system", "content": search_ctx})
                logger.info(f"[CHAT] Injected {len(search_data['results'])} live web search results into prompt context.")
            else:
                temporal_ctx = WebSearchEngine.get_temporal_header()
                messages.insert(0, {"role": "system", "content": temporal_ctx})
        except Exception as se:
            logger.warning(f"[CHAT] Web search execution error: {se}")
            temporal_ctx = WebSearchEngine.get_temporal_header()
            messages.insert(0, {"role": "system", "content": temporal_ctx})
    else:
        temporal_ctx = WebSearchEngine.get_temporal_header()
        messages.insert(0, {"role": "system", "content": temporal_ctx})

    # Determine model
    target_model = payload.model or model_mgr.active_model_id
    if not target_model:
        avail_models = await model_mgr.list_all_models()
        if avail_models:
            target_model = avail_models[0]["id"]
            model_mgr.active_model_id = target_model
            model_mgr.is_loaded = True

    if not target_model:
        logger.warning("[SERVER] No local model available")
        raise HTTPException(
            status_code=503,
            detail="AI MODEL OFFLINE\nNo model is currently loaded or available on the host."
        )

    logger.info(f"[SERVER] Model: {target_model}")

    # Verify runtime is available
    if not await model_mgr.current_adapter.is_available():
        logger.warning("[SERVER] Model adapter runtime unavailable")
        raise HTTPException(
            status_code=503,
            detail="AI MODEL OFFLINE\nThe selected model could not be loaded.\nCheck the AIR AI Host dashboard."
        )

    # Concurrency control: acquire queue slot
    await model_mgr.queue.acquire()
    logger.info("[MODEL] Generation started")

    async def token_generator():
        try:
            # Emit search results metadata if web search was performed
            if search_data and search_data.get("success"):
                search_event = json.dumps({
                    "type": "search_results",
                    "query": search_data["query"],
                    "results": search_data["results"],
                    "conversation_id": conv_id
                })
                yield f"data: {search_event}\n\n"

            async for token in model_mgr.current_adapter.chat_stream(
                model_id=target_model,
                messages=messages,
                temperature=payload.temperature or 0.7
            ):
                model_mgr.queue.record_token()
                # Server-Sent Events format
                data = json.dumps({"token": token, "done": False, "model": target_model, "conversation_id": conv_id})
                yield f"data: {data}\n\n"
            
            # Send done event
            data = json.dumps({"token": "", "done": True, "model": target_model, "conversation_id": conv_id})
            yield f"data: {data}\n\n"
            logger.info("[MODEL] Generation completed")
            logger.info("[SERVER] Response sent")
        except Exception as e:
            logger.error(f"[MODEL] Generation error: {e}")
            err_data = json.dumps({"error": f"AI Engine Error: {str(e)}", "done": True})
            yield f"data: {err_data}\n\n"
        finally:
            model_mgr.queue.release()

    if payload.stream:
        return StreamingResponse(token_generator(), media_type="text/event-stream")
    else:
        # Non-streaming buffer
        output_tokens = []
        try:
            async for token in model_mgr.current_adapter.chat_stream(
                model_id=target_model,
                messages=messages,
                temperature=payload.temperature or 0.7
            ):
                model_mgr.queue.record_token()
                output_tokens.append(token)
            
            logger.info("[MODEL] Generation completed")
            logger.info("[SERVER] Response sent")
            res_payload = {
                "response": "".join(output_tokens),
                "model": target_model,
                "conversation_id": conv_id
            }
            if search_data and search_data.get("success"):
                res_payload["search_results"] = search_data["results"]
            return res_payload
        except Exception as e:
            logger.error(f"[MODEL] Generation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            model_mgr.queue.release()

# ── Model Test Endpoint (Host / Diagnostics) ───────────────────

@router.post("/test-inference")
async def test_inference(payload: TestInferenceRequest, request: Request):
    """
    Directly test the actual local model with a prompt.
    Returns: {"success": true, "response": "...", "model": "..."}
    """
    model_mgr: ModelManager = request.app.state.model_manager
    target_model = model_mgr.active_model_id
    if not target_model:
        avail = await model_mgr.list_all_models()
        if avail:
            target_model = avail[0]["id"]
            model_mgr.active_model_id = target_model
            model_mgr.is_loaded = True

    if not target_model:
        return {"success": False, "error": "No AI model loaded on host."}

    user_prompt = payload.prompt or "Say hello"
    tokens = []
    try:
        await model_mgr.queue.acquire()
        async for token in model_mgr.current_adapter.chat_stream(
            model_id=target_model,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.7
        ):
            tokens.append(token)
        return {
            "success": True,
            "response": "".join(tokens).strip(),
            "model": target_model,
            "prompt": user_prompt
        }
    except Exception as e:
        return {"success": False, "error": str(e), "model": target_model}
    finally:
        model_mgr.queue.release()

# ── Chat & Settings Persistence ────────────────────────────────

@router.get("/chats")
async def get_chats(request: Request, authorization: Optional[str] = Header(None)):
    """Retrieve saved conversations."""
    auth_mgr: AuthManager = request.app.state.auth_manager
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
    token = get_request_token(request, authorization)

    if auth_mgr.require_pin and not auth_mgr.is_valid_session(token, client_ip):
        raise HTTPException(status_code=401, detail="Authentication required.")

    chats_file = request.app.state.chats_file
    if os.path.exists(chats_file):
        try:
            with open(chats_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

@router.post("/chats")
async def save_chats(request: Request, authorization: Optional[str] = Header(None)):
    """Save conversations to persistent storage."""
    auth_mgr: AuthManager = request.app.state.auth_manager
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
    token = get_request_token(request, authorization)

    if auth_mgr.require_pin and not auth_mgr.is_valid_session(token, client_ip):
        raise HTTPException(status_code=401, detail="Authentication required.")

    chats_file = request.app.state.chats_file
    try:
        body = await request.json()
        with open(chats_file, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2)
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/settings")
async def get_settings(request: Request):
    """Retrieve UI and inference settings."""
    settings_file = request.app.state.settings_file
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"temperature": 0.7, "globalSystemPrompt": "", "theme": "dark"}

@router.post("/settings")
async def save_settings(request: Request, authorization: Optional[str] = Header(None)):
    """Update settings."""
    auth_mgr: AuthManager = request.app.state.auth_manager
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
    token = get_request_token(request, authorization)

    if auth_mgr.require_pin and not auth_mgr.is_valid_session(token, client_ip):
        raise HTTPException(status_code=401, detail="Authentication required.")

    settings_file = request.app.state.settings_file
    try:
        body = await request.json()
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2)
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/search")
async def web_search_get(q: str):
    """Direct Web Search API endpoint."""
    return WebSearchEngine.search(q, max_results=5)

@router.post("/search")
async def web_search_post(payload: Dict[str, Any]):
    """Direct Web Search API endpoint."""
    q = payload.get("q") or payload.get("query", "")
    return WebSearchEngine.search(q, max_results=5)

