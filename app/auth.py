"""API key authentication for Ark Opus endpoints."""
import hashlib
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from .database import get_db
from .models import ApiKey

_api_key_header = APIKeyHeader(name='X-API-Key', auto_error=False)


async def verify_api_key(
    api_key: str | None = Depends(_api_key_header),
    db: Session = Depends(get_db),
) -> str:
    """Validate API key and return associated profile_name. Raises 401 if invalid."""
    if not api_key:
        raise HTTPException(status_code=401, detail='Missing API key')

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    row = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active == True,
    ).first()

    if not row:
        raise HTTPException(status_code=401, detail='Invalid API key')

    return row.profile_name
