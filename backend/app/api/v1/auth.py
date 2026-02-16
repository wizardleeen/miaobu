from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import secrets

from ...database import get_db
from ...models import User
from ...schemas import Token, UserResponse
from ...services.github import GitHubService
from ...core.security import create_access_token, get_current_user
from ...core.exceptions import UnauthorizedException
from ...config import get_settings

settings = get_settings()

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
    """Handle GitHub OAuth callback and redirect to frontend."""
    try:
        print(f"[DEBUG] GitHub callback started with code: {code[:20]}...")

        # Exchange code for access token
        access_token = await GitHubService.exchange_code_for_token(code)
        print(f"[DEBUG] Got access token: {access_token[:20] if access_token else 'None'}...")
        if not access_token:
            raise UnauthorizedException("Failed to get access token from GitHub")

        # Get user info from GitHub
        github_user = await GitHubService.get_user_info(access_token)
        print(f"[DEBUG] Got GitHub user: {github_user.get('login')}")

        # Find or create user in database
        user = db.query(User).filter(User.github_id == github_user["id"]).first()

        if user:
            # Update existing user
            user.github_username = github_user["login"]
            user.github_email = github_user.get("email")
            user.github_avatar_url = github_user["avatar_url"]
            user.github_access_token = access_token  # TODO: Encrypt in production
            print(f"[DEBUG] Updated existing user: {user.id}")
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
            print(f"[DEBUG] Created new user")

        db.commit()
        db.refresh(user)
        print(f"[DEBUG] Database commit successful, user.id: {user.id}")

        # Create JWT token
        jwt_token = create_access_token(data={"sub": str(user.id)})
        print(f"[DEBUG] Created JWT token: {jwt_token[:50]}...")

        # Redirect to frontend with token
        frontend_url = f"{settings.frontend_url}/auth/callback?token={jwt_token}"
        print(f"[DEBUG] Redirecting to: {frontend_url[:80]}...")
        return RedirectResponse(url=frontend_url)

    except Exception as e:
        # Redirect to frontend with error
        print(f"[ERROR] Exception in github_callback: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        # Get error message from HTTPException.detail or str(e)
        error_message = getattr(e, 'detail', str(e)) or 'Authentication failed'
        error_url = f"{settings.frontend_url}/auth/callback?error={error_message}"
        print(f"[ERROR] Redirecting to error URL: {error_url}")
        return RedirectResponse(url=error_url)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user information."""
    return current_user
