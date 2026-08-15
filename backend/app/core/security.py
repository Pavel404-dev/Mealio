import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import get_settings


_password_hasher = PasswordHash.recommended()
_OPAQUE_TOKEN_BYTES = 48


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


def _generate_opaque_token() -> str:
    return secrets.token_urlsafe(_OPAQUE_TOKEN_BYTES)


def _hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_refresh_token() -> str:
    return _generate_opaque_token()


def hash_refresh_token(refresh_token: str) -> str:
    return _hash_opaque_token(refresh_token)


def generate_password_reset_token() -> str:
    return _generate_opaque_token()


def hash_password_reset_token(reset_token: str) -> str:
    return _hash_opaque_token(reset_token)


def generate_email_verification_token() -> str:
    return _generate_opaque_token()


def hash_email_verification_token(verification_token: str) -> str:
    return _hash_opaque_token(verification_token)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()

    now = datetime.now(UTC)

    expire = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()

    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
