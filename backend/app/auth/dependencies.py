"""FastAPI dependencies that enforce authentication and roles on the server.

Use ``require_role(Role.X)`` on every route that needs a login. The frontend may hide
buttons a role can't use, but that is only cosmetic: these checks are what actually
protect the endpoints.

The user is reloaded from the database on every request (these are sync dependencies, so
FastAPI runs them in its threadpool), which means deactivating a user, changing their
role or bumping their token_version takes effect on their very next request.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from app.auth.roles import Role
from app.auth.tokens import InvalidTokenError, TokenType, decode_token
from app.core.config import Settings, app_settings
from app.db.models import User
from app.db.session import get_session

bearer = HTTPBearer(auto_error=False, description="Access token from POST /api/auth/login")

UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers=UNAUTHORIZED_HEADERS)


def user_from_token(
    session: Session, settings: Settings, token: str, expected_type: TokenType = "access"
) -> User:
    """Validate a token and return its active user, or raise InvalidTokenError."""
    claims = decode_token(settings, token, expected_type)
    user = session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise InvalidTokenError("User not found or inactive")
    if user.token_version != claims.token_version:
        raise InvalidTokenError("Token has been revoked")
    return user


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> User:
    if credentials is None:
        raise _unauthorized()
    try:
        user = user_from_token(session, settings, credentials.credentials)
    except InvalidTokenError:
        raise _unauthorized("Invalid or expired token") from None
    session.expunge(user)  # usable after the request's session closes
    return user


def require_role(required: Role) -> Callable[..., User]:
    """Dependency factory: 401 without a valid token, 403 if the role is too low."""

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not Role(user.role).allows(required):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Requires the {required.value} role or higher"
            )
        return user

    dependency.__name__ = f"require_{required.value}"
    return dependency


Viewer = Annotated[User, Depends(require_role(Role.VIEWER))]
Operator = Annotated[User, Depends(require_role(Role.OPERATOR))]
Supervisor = Annotated[User, Depends(require_role(Role.SUPERVISOR))]


def websocket_user(websocket: WebSocket, token: str | None) -> User | None:
    """Authenticate a WebSocket. Browsers can't set headers on a WebSocket, so the access
    token comes in the ``token`` query parameter. Sync: call it via asyncio.to_thread."""
    if not token:
        return None
    factory: sessionmaker[Session] = websocket.app.state.session_factory
    settings: Settings = websocket.app.state.settings
    with factory() as session:
        try:
            user = user_from_token(session, settings, token)
        except InvalidTokenError:
            return None
        session.expunge(user)
        return user
