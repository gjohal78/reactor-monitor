"""Password hashing with bcrypt (used directly; passlib is unmaintained).

bcrypt only uses the first 72 bytes of a password, and bcrypt >= 5 refuses longer input
outright. Over-long passwords are rejected when an account is created and simply fail
verification at login, rather than being silently truncated.
"""

from functools import cache

import bcrypt

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72


class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise PasswordPolicyError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")


def hash_password(password: str, rounds: int = 12) -> str:
    validate_password(password)
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode()
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode())


@cache
def dummy_hash(rounds: int) -> str:
    """Checked against when the username does not exist, so a login for an unknown user
    takes as long as one with a wrong password and response timing does not reveal which
    usernames exist. Same work factor as real hashes; computed once per work factor."""
    return bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds)).decode()
