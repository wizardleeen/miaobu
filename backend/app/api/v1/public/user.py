"""Public API — User endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ....database import get_db
from ....models import User
from ....core.security import get_current_user_flexible
from .helpers import single_response

router = APIRouter(tags=["Public API - User"])


@router.get("/user")
async def get_user(
    current_user: User = Depends(get_current_user_flexible),
):
    """Get the authenticated user's profile."""
    return single_response({
        "id": current_user.id,
        "github_username": current_user.github_username,
        "github_email": current_user.github_email,
        "github_avatar_url": current_user.github_avatar_url,
        "created_at": current_user.created_at.isoformat(),
    })
