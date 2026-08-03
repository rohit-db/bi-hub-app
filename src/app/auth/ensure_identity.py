import chainlit as cl
from config import settings
from auth.identity import Identity, OboTokenSource, PatTokenSource
from typing import Dict, Optional
from utils.logging import logger
import jwt
import datetime


# Treat a token as expired this many seconds BEFORE its real exp. The Genie MCP
# endpoint rejects tokens that are valid but near expiry (observed 403 at ~100s
# left), so we proactively refuse near-expiry tokens and surface a clean
# "session expired" prompt instead of a raw 403 mid-request.
TOKEN_EXPIRY_MARGIN_SECONDS = 120


def _is_token_expired(token: str, margin_seconds: int = TOKEN_EXPIRY_MARGIN_SECONDS) -> bool:
    """Check if the OBO token is expired (or within margin_seconds of expiring)."""
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp = datetime.datetime.fromtimestamp(decoded["exp"], datetime.timezone.utc)
        time_left = (exp - datetime.datetime.now(datetime.timezone.utc)).total_seconds()

        if time_left <= margin_seconds:
            logger.warning(
                f"[AUTH] Token expired or near expiry ({time_left:.0f}s left, "
                f"margin {margin_seconds}s) — treating as expired")
            return True
        else:
            logger.info(f"[AUTH] Token valid for {time_left} more seconds")
            return False
    except Exception as e:
        logger.error(f"[AUTH] Error checking token expiration: {e}")
        return True  # Assume expired if we can't decode

async def ensure_identity():
    """Ensure we have valid authentication headers ready for the chat session"""
    if not cl.context.session:
        logger.error("No session context available")
        return None
        
    user = cl.context.session.user
    if not user:
        logger.warning("User not found for this session. Please login again.")
        return None

    # For PAT auth, it's simple - just use the configured PAT
    if settings.enable_password_auth:
        logger.info("[AUTH] Using PAT authentication")
        return Identity(
            email=getattr(user, 'email', None),
            display_name=user.display_name,
            auth_type="pat",
            token_source=PatTokenSource(settings.pat)
        )

    # For OBO auth, we need to get valid headers
    auth_type = "obo"
    token_source = None
    
    # Try to get stored headers from user metadata first (preferred)
    if user.metadata:
        stored_token = user.metadata.get("obo_token")
        stored_headers = user.metadata.get("headers")
        
        if stored_token and stored_headers:
            # Check if stored token is still valid
            if _is_token_expired(stored_token):
                logger.error("[AUTH] Stored OBO token is expired - session is over")
                return None
            
            # Use stored headers
            def _stored_headers_getter() -> Dict[str, str]:
                return stored_headers
            
            token_source = OboTokenSource(_stored_headers_getter)
            logger.info("[AUTH] Using stored OBO token and headers")
        else:
            logger.warning("[AUTH] No stored OBO token/headers found")
    
    # If no stored headers available, we can't proceed
    if not token_source:
        logger.error("[AUTH] No stored OBO token/headers available - user needs to re-authenticate")
        return None
    
    # Validate we have a valid token
    token = token_source.bearer_token()
    if not token:
        logger.error("[AUTH] No OBO token found in headers")
        return None
        
    if _is_token_expired(token):
        logger.error("[AUTH] OBO token is expired - session is over. Please re-authenticate.")
        return None

    logger.info("[AUTH] Valid authentication headers ready")
    return Identity(
        email=getattr(user, 'email', None),
        display_name=user.display_name,
        auth_type=auth_type,
        token_source=token_source
    )
