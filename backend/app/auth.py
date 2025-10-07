import os
import hmac
import hashlib
from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader

# =========================
# Load secrets from env
# =========================
API_KEY = os.getenv("API_KEY")
HMAC_SECRET = os.getenv("HMAC_SECRET")

# Header definitions
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)
signature_header = APIKeyHeader(name="X-Signature", auto_error=False)

# =========================
# API Key check
# =========================
async def require_api_key(api_key: str = Security(api_key_header)):
    """Ensures the correct API key is provided in X-API-KEY header."""
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured on server")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True

# =========================
# HMAC verification
# =========================
async def verify_hmac(request: Request, signature: str = Security(signature_header)):
    """
    Verifies an HMAC signature header (X-Signature) for incoming POST requests.
    Used for simulators or IoT devices that sign payloads.
    """
    if not HMAC_SECRET:
        raise HTTPException(status_code=500, detail="HMAC_SECRET not configured on server")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Signature header")

    # Read the request body
    body = await request.body()
    expected = hmac.new(
        HMAC_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    # Secure constant-time comparison
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    return True
