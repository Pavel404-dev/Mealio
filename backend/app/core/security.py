from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import get_settings

_password_hasher = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    return _password_hasher.hash(plain_password)


def verify_password(
        plain_password: str,
        hashed_password: str | None,
) -> bool:
    if not hashed_password:
        return False

    try:
        return _password_hasher.verify(
            plain_password,
            hashed_password,
        )
    except UnknownHashError:
        return False


def create_access_token(
        subject: str,
        expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()

    expire = datetime.now(UTC) + (
            expires_delta
            or timedelta(minutes=settings.access_token_expire_minutes)
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )