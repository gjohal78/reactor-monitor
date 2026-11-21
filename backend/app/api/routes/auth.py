"""Login, token refresh and current user."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.audit.log import AuditAction, write_audit
from app.auth.dependencies import UNAUTHORIZED_HEADERS, Viewer, user_from_token
from app.auth.passwords import dummy_hash, verify_password
from app.auth.tokens import InvalidTokenError, create_token
from app.auth.users import get_user_by_username
from app.core.config import Settings, app_settings
from app.db.models import User
from app.db.session import get_session
from app.schemas import RefreshIn, TokenPair, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

SettingsDep = Annotated[Settings, Depends(app_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def get_clock(request: Request) -> Callable[[], datetime]:
    clock: Callable[[], datetime] = request.app.state.clock
    return clock


def issue_tokens(settings: Settings, user: User) -> TokenPair:
    def token(kind: str) -> str:
        return create_token(
            settings,
            user_id=user.id,
            token_version=user.token_version,
            token_type="access" if kind == "access" else "refresh",
        )

    return TokenPair(
        access_token=token("access"),
        refresh_token=token("refresh"),
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/login", response_model=TokenPair)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    clock: Annotated[Callable[[], datetime], Depends(get_clock)],
) -> TokenPair:
    """Exchange username + password (form fields, OAuth2 password flow) for tokens.

    Every attempt, successful or not, is written to the audit log. Failures always say
    "Incorrect username or password", whether the user is unknown, the password is wrong
    or the account is disabled, so the response doesn't reveal which usernames exist.
    """
    user = get_user_by_username(session, form.username)
    password_ok = verify_password(
        form.password, user.password_hash if user else dummy_hash(settings.bcrypt_rounds)
    )
    if user is None:
        reason = "unknown user"
    elif not password_ok:
        reason = "wrong password"
    elif not user.is_active:
        reason = "account disabled"
    else:
        reason = None

    write_audit(
        session,
        timestamp=clock(),
        action=AuditAction.LOGIN,
        user=user,
        username=form.username,
        success=reason is None,
        detail=reason,
        client_ip=request.client.host if request.client else None,
    )
    session.commit()

    if reason is not None or user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password",
            headers=UNAUTHORIZED_HEADERS,
        )
    return issue_tokens(settings, user)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshIn, session: SessionDep, settings: SettingsDep) -> TokenPair:
    """Trade a valid refresh token for a new access + refresh pair."""
    try:
        user = user_from_token(session, settings, body.refresh_token, expected_type="refresh")
    except InvalidTokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired refresh token",
            headers=UNAUTHORIZED_HEADERS,
        ) from None
    return issue_tokens(settings, user)


@router.get("/me", response_model=UserOut)
def me(user: Viewer) -> UserOut:
    return UserOut.model_validate(user)
