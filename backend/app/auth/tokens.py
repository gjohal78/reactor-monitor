"""JWT access and refresh tokens.

- Access token: short-lived (15 min), sent as ``Authorization: Bearer ...`` on every request.
- Refresh token: long-lived (7 days), only accepted by POST /api/auth/refresh, which returns
  a fresh pair.

Each token carries a ``type`` claim, so a refresh token can't be used as an access token or
the other way round. It also carries the user's ``token_version``: bumping that column
(e.g. on password change or deactivation) invalidates every token already issued to that
user. The role is deliberately *not* trusted from the token: the dependencies load the user
from the database on each request, so a role change or deactivation applies immediately.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt

from app.core.config import Settings

TokenType = Literal["access", "refresh"]


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: int
    token_version: int
    type: TokenType


def create_token(
    settings: Settings,
    *,
    user_id: int,
    token_version: int,
    token_type: TokenType,
    now: datetime | None = None,
) -> str:
    issued = now or datetime.now(UTC)
    lifetime = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "type": token_type,
        "iat": issued,
        "exp": issued + lifetime,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(settings: Settings, token: str, expected_type: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],  # pinned: never trust the header's "alg"
            options={"require": ["sub", "exp", "iat", "type", "ver"]},
        )
    except jwt.PyJWTError as error:
        raise InvalidTokenError(str(error)) from None
    if payload["type"] != expected_type:
        raise InvalidTokenError(f"Expected a {expected_type} token")
    try:
        return TokenClaims(
            user_id=int(payload["sub"]), token_version=int(payload["ver"]), type=expected_type
        )
    except (TypeError, ValueError):
        raise InvalidTokenError("Malformed token claims") from None
