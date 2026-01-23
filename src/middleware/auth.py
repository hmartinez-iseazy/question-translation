import secrets
from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from src.config.settings import get_settings

settings = get_settings()

api_key_header = APIKeyHeader(
    name=settings.api_key_header,
    auto_error=False,
    description="API Key for authentication"
)


async def verify_api_key(
    request: Request,
    api_key: str = Security(api_key_header)
) -> str:
    """
    Verify the API key from the request header.

    If no API key is configured in settings, authentication is disabled.
    """
    # If no API key configured, skip authentication (development mode)
    if not settings.api_key:
        return "anonymous"

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Use secrets.compare_digest to prevent timing attacks
    if not secrets.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
        )

    return api_key
