from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import secrets

from ...database import get_db
from ...models import User
from ...schemas import Token, UserResponse
from ...services.github import GitHubService
from ...core.security import create_access_token, get_current_user
from ...core.exceptions import UnauthorizedException

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/github/login")
async def github_login():
    """Initiate GitHub OAuth flow."""
    state = secrets.token_urlsafe(32)
    # In production, store state in Redis with expiration and verify it in callback
    oauth_url = await GitHubService.get_oauth_url(state)
    return {"url": oauth_url, "state": state}


@router.get("/github/callback")
async def github_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db)
):
    """Handle GitHub OAuth callback."""
    try:
        # Exchange code for access token
        access_token = await GitHubService.exchange_code_for_token(code)
        if not access_token:
            raise UnauthorizedException("Failed to get access token from GitHub")

        # Get user info from GitHub
        github_user = await GitHubService.get_user_info(access_token)

        # Find or create user in database
        user = db.query(User).filter(User.github_id == github_user["id"]).first()

        if user:
            # Update existing user
            user.github_username = github_user["login"]
            user.github_email = github_user.get("email")
            user.github_avatar_url = github_user["avatar_url"]
            user.github_access_token = access_token  # TODO: Encrypt in production
        else:
            # Create new user
            user = User(
                github_id=github_user["id"],
                github_username=github_user["login"],
                github_email=github_user.get("email"),
                github_avatar_url=github_user["avatar_url"],
                github_access_token=access_token  # TODO: Encrypt in production
            )
            db.add(user)

        db.commit()
        db.refresh(user)

        # Create JWT token
        jwt_token = create_access_token(data={"sub": user.id})

        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user information."""
    return current_user
