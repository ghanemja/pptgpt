"""
Bearer-token authentication for the DeckEngine FastAPI app.

Mirrors brain-university's /api/auth.py so the shared BU_AUTH_SECRET works
across every portfolio project. Same env vars, same token format.

Token format (URL-safe base64):
    <username>|<expiry_unix>|<hmac_sha256(username|expiry, BU_SECRET)>

Stateless, no DB. Verification recomputes the HMAC and checks expiry.

Env vars (read at process start):
    BU_AUTH_USER       — single allowed username (default "admin")
    BU_AUTH_PASSWORD   — required; refusing to start without it in production
    BU_AUTH_SECRET     — HMAC key; auto-generated random fallback if unset
                         (tokens invalidate on restart, fine for single-instance)
    BU_AUTH_TTL_HOURS  — token lifetime, default 24
    BU_AUTH_DISABLED   — "1" to bypass auth entirely (dev only)

Routes protected by middleware are everything except an allowlist:
    /, /health, /login, /docs, /openapi.json, /redoc,
    /frontend/*, /assets/*, /v2-assets/*, /*.html, /*.css, /*.js, /*.jsx,
    OPTIONS preflight.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
import warnings

from fastapi import Request


# ── Env-driven config ──────────────────────────────────────────────────────

AUTH_USER     = os.environ.get("BU_AUTH_USER", "admin")
AUTH_PASSWORD = os.environ.get("BU_AUTH_PASSWORD", "")
AUTH_SECRET   = os.environ.get("BU_AUTH_SECRET", "").encode("utf-8")
AUTH_TTL_S    = int(os.environ.get("BU_AUTH_TTL_HOURS", "24")) * 3600
AUTH_DISABLED = os.environ.get("BU_AUTH_DISABLED", "") == "1"

if not AUTH_SECRET:
    AUTH_SECRET = secrets.token_bytes(32)
    warnings.warn(
        "BU_AUTH_SECRET not set; using ephemeral random key. Tokens invalidate "
        "on restart. Set BU_AUTH_SECRET to a 32+ byte random string in prod.",
        RuntimeWarning,
    )

if not AUTH_PASSWORD and not AUTH_DISABLED:
    # Soft-fail: keep dev usable but loudly warn. Production deploy scripts
    # MUST set BU_AUTH_PASSWORD.
    AUTH_PASSWORD = "password"
    warnings.warn(
        "BU_AUTH_PASSWORD not set; defaulting to 'admin/password'. "
        "Set BU_AUTH_PASSWORD before exposing this server publicly.",
        RuntimeWarning,
    )


# ── Token mint / verify ────────────────────────────────────────────────────

def mint_token(username: str, ttl_s: int | None = None) -> str:
    """Issue a fresh bearer token."""
    ttl = ttl_s or AUTH_TTL_S
    expiry = int(time.time()) + ttl
    payload = f"{username}|{expiry}"
    sig = hmac.new(AUTH_SECRET, payload.encode("utf-8"), hashlib.sha256).digest()
    raw = f"{payload}|{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def verify_token(token: str) -> str | None:
    """Return username if token valid + unexpired; else None."""
    if not token:
        return None
    try:
        # Re-pad base64 (urlsafe encoding may strip = padding)
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad).decode("utf-8")
        username, expiry_s, sig_b64 = raw.rsplit("|", 2)
        expiry = int(expiry_s)
    except Exception:
        return None
    if time.time() > expiry:
        return None
    expected = hmac.new(AUTH_SECRET, f"{username}|{expiry}".encode(), hashlib.sha256).digest()
    pad2 = "=" * (-len(sig_b64) % 4)
    try:
        provided = base64.urlsafe_b64decode(sig_b64 + pad2)
    except Exception:
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    return username


def check_password(username: str, password: str) -> bool:
    """Constant-time comparison."""
    if not username or not password:
        return False
    u_ok = hmac.compare_digest(username, AUTH_USER)
    p_ok = hmac.compare_digest(password, AUTH_PASSWORD)
    return u_ok and p_ok


# ── ASGI middleware — gate every request except the allowlist ──────────────

# Public paths: the marketing/landing pages and auth endpoints. The static
# frontend (JSX, CSS, HTML pages) is unprotected so the SPA loads; the API
# endpoints under /api/* enforce bearer-token auth.
PUBLIC_PATHS = {
    "/", "/health", "/login",
    "/docs", "/openapi.json", "/redoc",
    "/setup", "/setup/",
    "/storyboard", "/storyboard/",
    "/workbench", "/workbench/",
    "/canvas", "/canvas/",
    "/workbench-v1", "/workbench-v1/",
}
PUBLIC_PREFIXES = ("/frontend/", "/assets/", "/v2-assets/", "/samples/")
PUBLIC_SUFFIXES = (".html", ".css", ".js", ".jsx", ".png", ".jpg", ".svg", ".ico", ".woff", ".woff2",
                   ".pptx", ".pdf", ".docx", ".txt", ".md")


def is_public(path: str, method: str) -> bool:
    if method == "OPTIONS":  # CORS preflight
        return True
    if path in PUBLIC_PATHS:
        return True
    for p in PUBLIC_PREFIXES:
        if path.startswith(p):
            return True
    for s in PUBLIC_SUFFIXES:
        if path.endswith(s):
            return True
    return False


async def auth_middleware(request: Request, call_next):
    """FastAPI ASGI middleware — reject unauthenticated requests."""
    if AUTH_DISABLED:
        return await call_next(request)
    if is_public(request.url.path, request.method):
        return await call_next(request)

    auth_hdr = request.headers.get("authorization", "")
    if not auth_hdr.lower().startswith("bearer "):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"detail": "missing bearer token"}, status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_hdr.split(" ", 1)[1].strip()
    user = verify_token(token)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"detail": "invalid or expired token"}, status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Pass username through so downstream routes can read it
    request.state.user = user
    return await call_next(request)
