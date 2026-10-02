import os
import re
import secrets
import logging
from pathlib import Path
from typing import Optional, Tuple, Set

logger = logging.getLogger("hs_ai.security.sanitizer")

# Strict set of allowed file extensions
ALLOWED_EXTENSIONS: Set[str] = {
    ".txt", ".md", ".json", ".csv", ".py", ".js", ".html", ".css", ".pdf",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"
}

# Strict set of allowed MIME types
ALLOWED_MIME_TYPES: Set[str] = {
    "text/plain", "text/markdown", "application/json", "text/csv",
    "text/x-python", "text/javascript", "text/html", "text/css", "application/pdf",
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp",
    "application/octet-stream"
}

# Maximum lengths
MAX_PROMPT_LENGTH = 32768        # 32K characters
MAX_CONVERSATION_ID_LEN = 64
MAX_MODEL_NAME_LEN = 128
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

# Regex patterns for identifiers
CONV_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")
MODEL_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\:\/]{1,128}$")
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{16,64}$")

def validate_prompt(prompt: Optional[str]) -> Tuple[bool, str]:
    """Validate prompt presence and length."""
    if not prompt or not isinstance(prompt, str):
        return False, "Prompt must be a non-empty string."
    cleaned = prompt.strip()
    if not cleaned:
        return False, "Prompt cannot be whitespace only."
    if len(prompt) > MAX_PROMPT_LENGTH:
        return False, f"Prompt exceeds maximum allowed length of {MAX_PROMPT_LENGTH} characters."
    return True, ""

def validate_conversation_id(conv_id: Optional[str]) -> Tuple[bool, str]:
    """Validate conversation ID format."""
    if not conv_id:
        return True, ""  # Optional
    if not CONV_ID_PATTERN.match(conv_id):
        return False, "Invalid conversation ID format. Alphanumeric and dashes only."
    return True, ""

def validate_model_name(model_name: Optional[str]) -> Tuple[bool, str]:
    """Validate model identifier format."""
    if not model_name:
        return True, ""
    if not MODEL_ID_PATTERN.match(model_name):
        return False, "Invalid model name format."
    return True, ""

def validate_session_token(token: Optional[str]) -> Tuple[bool, str]:
    """Validate session token format."""
    if not token:
        return False, "Session token is required."
    if not SESSION_ID_PATTERN.match(token):
        return False, "Malformed session token format."
    return True, ""

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename strictly preventing directory traversal, null bytes,
    absolute paths, or dangerous OS characters.
    """
    if not filename:
        return f"file_{secrets.token_hex(4)}.bin"

    # Strip directory components (both Unix and Windows style)
    clean = os.path.basename(filename.replace("\\", "/"))
    clean = clean.split("/")[-1].split("\\")[-1]

    # Block explicit traversal sequences
    clean = clean.replace("..", "").replace("/", "").replace("\\", "").replace("\x00", "")

    # Restrict to safe characters
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean)
    if not clean or clean.startswith("."):
        clean = f"upload_{clean}"

    # Enforce maximum length
    return clean[:100]

def is_allowed_file(filename: str) -> bool:
    """Check if file extension is strictly permitted."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def validate_upload(
    content: bytes,
    filename: str,
    content_type: Optional[str] = None,
    max_mb: int = 20
) -> Tuple[bool, str]:
    """
    Validate an uploaded file:
      1. Size limit
      2. File extension
      3. Content type
      4. Traversal protection
    """
    max_bytes = max_mb * 1024 * 1024
    if len(content) > max_bytes:
        return False, f"File exceeds maximum allowed size of {max_mb} MB."

    if not is_allowed_file(filename):
        return False, f"File type not permitted. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

    if content_type and content_type.lower() not in ALLOWED_MIME_TYPES:
        return False, f"MIME type '{content_type}' is not accepted."

    return True, ""

def validate_upload_size(content: bytes, max_mb: int = 20) -> bool:
    """Check if uploaded bytes are within size limits."""
    return len(content) <= (max_mb * 1024 * 1024)

def get_isolated_upload_dir(base_data_dir: Path, session_id: str) -> Path:
    """
    Generate or return a secure isolated upload path scoped strictly to the session:
    data/uploads/<sanitized-session-dir>/
    """
    # Sanitize session_id to prevent any directory breakout
    safe_session = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)[:40]
    if not safe_session:
        safe_session = secrets.token_hex(16)

    upload_root = (base_data_dir / "uploads" / safe_session).resolve()

    # Safety assertion: verify resolved path is strictly within base_data_dir / "uploads"
    base_uploads_resolved = (base_data_dir / "uploads").resolve()
    upload_root.mkdir(parents=True, exist_ok=True)

    try:
        upload_root.relative_to(base_uploads_resolved)
    except ValueError:
        raise PermissionError("Path traversal attempt detected in upload directory resolution.")

    return upload_root
