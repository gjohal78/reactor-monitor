"""User lookup and creation."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.auth.roles import Role
from app.db.models import User


class UserExistsError(ValueError):
    pass


def get_user_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def create_user(
    session: Session, username: str, password: str, role: Role, *, rounds: int = 12
) -> User:
    """Create a user (password policy enforced). Caller commits."""
    username = username.strip()
    if not username or len(username) > 64:
        raise ValueError("Username must be 1-64 characters")
    if get_user_by_username(session, username) is not None:
        raise UserExistsError(f"User {username!r} already exists")
    user = User(
        username=username,
        password_hash=hash_password(password, rounds),
        role=role.value,
        is_active=True,
        token_version=0,
        created_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    return user
