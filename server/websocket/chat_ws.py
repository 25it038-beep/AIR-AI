import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..model_manager.manager import ModelManager
from ..device_manager.device_tracker import DeviceTracker
from ..security.firewall import Firewall
from ..security.rate_limiter import RateLimiter
from ..security.auth import AuthManager
from ..security.sanitizer import (
    validate_prompt,
    validate_conversation_id,
    validate_model_name
)
from ..web_search import WebSearchEngine

logger = logging.getLogger("hs_ai.chat_ws")

router = APIRouter(tags=["WebSocket Chat"])

# Global concurrent WebSocket counter
active_ws_connections = 0
MAX_CONCURRENT_WS = 32

@router.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    global active_ws_connections
    app = websocket.app
    model_mgr: ModelManager = app.state.model_manager
    device_tracker: DeviceTracker = app.state.device_tracker
    firewall: Firewall = app.state.firewall
    rate_limiter: RateLimiter = app.state.rate_limiter
    auth_mgr: AuthManager = app.state.auth_manager

    client_ip = websocket.client.host if websocket.client else "unknown"
    headers = dict(websocket.headers)
    user_agent = headers.get("user-agent", "")
    token = websocket.query_params.get("token") or headers.get("x-session-token")

    # 1. Firewall verification
    if firewall.is_blocked(client_ip):
        await websocket.accept()
        await websocket.send_json({"type": "error", "error": "Access blocked by Host administrator."})
        await websocket.close(code=4403)
        return

    # 2. Max concurrent WebSocket connections limit
    if active_ws_connections >= MAX_CONCURRENT_WS and client_ip not in ("127.0.0.1", "localhost", "::1"):
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "error": "Connection limit reached. Too many simultaneous devices connected to AIR AI."
        })
        await websocket.close(code=4429)
        return

    # 3. WebSocket Rate limit check on new connections
    allowed_ws, retry_after = rate_limiter.check_rate_limit(client_ip, "websocket")
    if not allowed_ws:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "error": f"Connection rate limit reached. Please wait {retry_after} seconds before reconnecting."
        })
        await websocket.close(code=4429)
        return

    # 4. Authentication verification
    if auth_mgr.require_pin and not auth_mgr.is_valid_session(token, client_ip):
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "auth_required": True,
            "error": "AUTHENTICATION REQUIRED\n\nPlease connect with the network PIN on the AIR AI portal."
        })
        await websocket.close(code=4401)
        return

    # Accept connection and track
    await websocket.accept()
    active_ws_connections += 1
    device_tracker.register_or_update(client_ip, user_agent)
    logger.info(f"[CLIENT WS CONNECTED] {client_ip} (Active WS: {active_ws_connections})")

    try:
        while True:
            raw_text = await websocket.receive_text()
            if not raw_text:
                continue

            try:
                data = json.loads(raw_text)
            except Exception:
                await websocket.send_json({"type": "error", "error": "Invalid JSON format."})
                continue

            msg_type = data.get("type", "chat")

            # Heartbeat ping
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # Check if session has expired during continuous connection
            if auth_mgr.require_pin and not auth_mgr.is_valid_session(token, client_ip):
                await websocket.send_json({
                    "type": "error",
                    "auth_required": True,
                    "error": "SESSION EXPIRED\n\nYour session has expired. Please reconnect to AIR AI."
                })
                await websocket.close(code=4401)
                return

            # Check message rate limiter (bucket: 'chat', 20/min)
            allowed_msg, retry_after = rate_limiter.check_rate_limit(client_ip, "chat")
            if not allowed_msg:
                await websocket.send_json({
                    "type": "error",
                    "error": f"TOO MANY REQUESTS\n\nPlease wait {retry_after} seconds before sending another message."
                })
                continue

            user_message = data.get("message") or data.get("prompt")
            conversation_id = data.get("conversation_id", "")
            target_model = data.get("model") or model_mgr.active_model_id
            temperature = data.get("temperature", 0.7)
            images = data.get("images", None)

            # Input validation
            valid_p, p_err = validate_prompt(user_message)
            if not valid_p:
                await websocket.send_json({"type": "error", "error": p_err})
                continue

            valid_c, c_err = validate_conversation_id(conversation_id)
            if not valid_c:
                await websocket.send_json({"type": "error", "error": c_err})
                continue

            if not target_model:
                avail_models = await model_mgr.list_all_models()
                if avail_models:
                    target_model = avail_models[0]["id"]
                    model_mgr.active_model_id = target_model
                    model_mgr.is_loaded = True

            # Section 16: Structured logging
            logger.info(f"[SERVER] Request received via WebSocket from {client_ip}")
            logger.info(f"[SERVER] Conversation: {conversation_id}")
            logger.info(f"[SERVER] Model: {target_model}")

            # Verify AI model readiness
            if not target_model:
                await websocket.send_json({
                    "type": "error",
                    "offline": True,
                    "error": "AI MODEL OFFLINE\n\nNo model is currently loaded.\nCheck the AIR AI Host dashboard."
                })
                continue

            if not await model_mgr.current_adapter.is_available():
                await websocket.send_json({
                    "type": "error",
                    "offline": True,
                    "error": "AI MODEL OFFLINE\n\nThe local AI engine is not responding.\nCheck the AIR AI Host dashboard."
                })
                continue

            # Construct message list
            user_payload = {"role": "user", "content": user_message}
            if images:
                user_payload["images"] = images
            messages = [user_payload]

            # Web Search Execution
            web_search = bool(data.get("web_search", False))
            if web_search and user_message:
                try:
                    await websocket.send_json({
                        "type": "status",
                        "status": "Searching the web...",
                        "model": target_model,
                        "conversation_id": conversation_id
                    })
                    search_data = WebSearchEngine.search(user_message, max_results=5)
                    if search_data.get("success"):
                        await websocket.send_json({
                            "type": "search_results",
                            "query": search_data["query"],
                            "results": search_data["results"],
                            "conversation_id": conversation_id
                        })
                        search_ctx = WebSearchEngine.format_search_context(search_data)
                        messages.insert(0, {"role": "system", "content": search_ctx})
                        logger.info(f"[WS CHAT] Injected {len(search_data['results'])} web search results into context.")
                except Exception as se:
                    logger.warning(f"[WS CHAT] Web search error: {se}")

            # Signal queue status to client
            await websocket.send_json({
                "type": "status",
                "status": "Generating...",
                "model": target_model,
                "conversation_id": conversation_id
            })

            # Concurrency queue slot
            await model_mgr.queue.acquire()
            logger.info("[MODEL] Generation started")

            try:
                async for token_text in model_mgr.current_adapter.chat_stream(
                    model_id=target_model,
                    messages=messages,
                    temperature=float(temperature)
                ):
                    model_mgr.queue.record_token()
                    await websocket.send_json({
                        "type": "token",
                        "token": token_text,
                        "conversation_id": conversation_id,
                        "model": target_model
                    })

                # Stream complete
                logger.info("[MODEL] Generation completed")
                await websocket.send_json({
                    "type": "done",
                    "conversation_id": conversation_id,
                    "model": target_model
                })
                logger.info("[SERVER] Response sent")

            except Exception as e:
                logger.error(f"[MODEL] Error during stream: {e}")
                await websocket.send_json({
                    "type": "error",
                    "error": f"Inference error: {str(e)}",
                    "conversation_id": conversation_id
                })
            finally:
                model_mgr.queue.release()

    except WebSocketDisconnect:
        logger.info(f"[CLIENT WS DISCONNECTED] {client_ip}")
    except Exception as e:
        logger.debug(f"WebSocket session ended: {e}")
    finally:
        active_ws_connections = max(0, active_ws_connections - 1)

