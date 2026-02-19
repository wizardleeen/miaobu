"""API Token management endpoints (JWT-only — dashboard use)."""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from ...database import get_db
from ...models import User, ApiToken
from ...schemas import ApiTokenCreate, ApiTokenResponse, ApiTokenCreated
from ...core.security import get_current_user, hash_api_token, API_TOKEN_PREFIX
from ...core.exceptions import NotFoundException

router = APIRouter(prefix="/tokens", tags=["API Tokens"])


@router.post("", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(
    data: ApiTokenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new API token. The full token is returned only once."""
    raw_token = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    token_hash = hash_api_token(raw_token)
    prefix = raw_token[:16]

    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

    api_token = ApiToken(
        user_id=current_user.id,
        name=data.name,
        token_hash=token_hash,
        prefix=prefix,
        expires_at=expires_at,
    )

    db.add(api_token)
    db.commit()
    db.refresh(api_token)

    return ApiTokenCreated(
        id=api_token.id,
        name=api_token.name,
        prefix=api_token.prefix,
        token=raw_token,
        last_used_at=api_token.last_used_at,
        expires_at=api_token.expires_at,
        created_at=api_token.created_at,
    )


@router.get("", response_model=List[ApiTokenResponse])
async def list_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all API tokens for the current user (prefix only, no secrets)."""
    tokens = (
        db.query(ApiToken)
        .filter(ApiToken.user_id == current_user.id)
        .order_by(ApiToken.created_at.desc())
        .all()
    )
    return tokens


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke (delete) an API token."""
    api_token = (
        db.query(ApiToken)
        .filter(ApiToken.id == token_id, ApiToken.user_id == current_user.id)
        .first()
    )

    if not api_token:
        raise NotFoundException("API token not found")

    db.delete(api_token)
    db.commit()
    return None
