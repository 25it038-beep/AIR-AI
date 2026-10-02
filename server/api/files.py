import os
import secrets
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, Header
from fastapi.responses import FileResponse

from ..security.auth import AuthManager
from ..security.rate_limiter import RateLimiter
from ..security.sanitizer import (
    sanitize_filename,
    validate_upload,
    get_isolated_upload_dir,
    MAX_FILE_SIZE_BYTES
)
from .security_api import get_request_token

logger = logging.getLogger("hs_ai.api.files")

router = APIRouter(prefix="/api/files", tags=["File Storage"])

@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """
    Secure isolated file upload endpoint.
    Enforces:
      - Active session validation (if PIN required)
      - Rate limiting (10 uploads/min per device)
      - Strict MIME type and extension validation
      - Maximum file size (20 MB)
      - Isolated per-session storage to prevent traversal
    """
    auth_mgr: AuthManager = request.app.state.auth_manager
    rate_limiter: RateLimiter = request.app.state.rate_limiter
    data_dir = Path(request.app.state.base_dir) / "data"

    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")

    # 1. Rate limiting
    allowed, retry_after = rate_limiter.check_rate_limit(client_ip, "file_upload")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Upload rate limit reached. Please wait {retry_after} seconds before uploading another file."
        )

    # 2. Authentication check
    token = get_request_token(request, authorization)
    if auth_mgr.require_pin and not auth_mgr.is_valid_session(token, client_ip):
        raise HTTPException(
            status_code=401,
            detail="Authentication required to upload files. Please authenticate on the AIR AI portal."
        )

    session_id = token or f"guest_{secrets.token_hex(8)}"

    # 3. Read content with size guard
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Error reading upload from {client_ip}: {e}")
        raise HTTPException(status_code=400, detail="Failed to read uploaded file.")

    # 4. Validate file type and size
    is_valid, err_msg = validate_upload(
        content=content,
        filename=file.filename or "unnamed.bin",
        content_type=file.content_type,
        max_mb=20
    )
    if not is_valid:
        logger.warning(f"Rejected invalid upload from {client_ip}: {err_msg}")
        raise HTTPException(status_code=400, detail=err_msg)

    # 5. Sanitize and generate safe server-side filename
    safe_orig = sanitize_filename(file.filename or "upload.bin")
    file_ext = os.path.splitext(safe_orig)[1].lower()
    random_prefix = secrets.token_hex(8)
    server_filename = f"{random_prefix}_{safe_orig}"

    # 6. Store in isolated session directory
    try:
        session_upload_dir = get_isolated_upload_dir(data_dir, session_id)
        target_path = session_upload_dir / server_filename

        with open(target_path, "wb") as f:
            f.write(content)

        logger.info(f"File stored safely: {target_path} ({len(content)} bytes) for {client_ip}")

        return {
            "success": True,
            "filename": server_filename,
            "original_name": safe_orig,
            "size_bytes": len(content),
            "url": f"/api/files/{session_id}/{server_filename}"
        }
    except PermissionError as pe:
        logger.error(f"Security violation during upload: {pe}")
        raise HTTPException(status_code=403, detail="Security violation: Path traversal prevented.")
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Internal error saving file.")

@router.get("/{session_id}/{filename}")
async def get_uploaded_file(
    session_id: str,
    filename: str,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Retrieve an uploaded file securely from its isolated session folder.
    Enforces strict path traversal defenses.
    """
    auth_mgr: AuthManager = request.app.state.auth_manager
    data_dir = Path(request.app.state.base_dir) / "data"

    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")

    # Path traversal defense
    safe_name = sanitize_filename(filename)
    try:
        session_dir = get_isolated_upload_dir(data_dir, session_id)
        file_path = (session_dir / safe_name).resolve()

        # Strict containment verification
        file_path.relative_to(session_dir)

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Requested file not found.")

        return FileResponse(path=str(file_path), filename=safe_name)
    except (ValueError, PermissionError):
        logger.warning(f"Path traversal attempted by {client_ip}: session={session_id}, file={filename}")
        raise HTTPException(status_code=403, detail="Forbidden access.")

