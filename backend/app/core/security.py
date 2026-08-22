import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import get_settings


_password_hasher = PasswordHash.recommended()
_OPAQUE_TOKEN_BYTES = 48
_EMAIL_OTP_DIGITS = 6
_EMAIL_OTP_CODE_SPACE = 10**_EMAIL_OTP_DIGITS
_EMAIL_OTP_DIGEST_DOMAIN = "mealio-email-otp-v1"
_MIN_EMAIL_OTP_PEPPER_BYTES = 32


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


def generate_email_otp_code() -> str:
    value = secrets.randbelow(_EMAIL_OTP_CODE_SPACE)
    return f"{value:0{_EMAIL_OTP_DIGITS}d}"


def _validate_email_otp_code(code: str) -> None:
    if not (len(code) == _EMAIL_OTP_DIGITS and code.isascii() and code.isdigit()):
        raise ValueError("Email OTP code must contain exactly 6 ASCII digits")


def hash_email_otp_code(
    *,
    code: str,
    otp_pepper: str,
    purpose: str,
    user_id: str,
    target_email: str,
) -> str:
    _validate_email_otp_code(code)

    normalized_purpose = purpose.strip()
    normalized_user_id = user_id.strip()
    normalized_email = target_email.strip().lower()

    if not normalized_purpose:
        raise ValueError("Email OTP purpose is required")
    if not normalized_user_id:
        raise ValueError("Email OTP user ID is required")
    if not normalized_email:
        raise ValueError("Email OTP target email is required")

    pepper_bytes = otp_pepper.encode("utf-8")
    if len(pepper_bytes) < _MIN_EMAIL_OTP_PEPPER_BYTES:
        raise ValueError("Email OTP pepper must contain at least 32 bytes")

    message = json.dumps(
        {
            "domain": _EMAIL_OTP_DIGEST_DOMAIN,
            "purpose": normalized_purpose,
            "user_id": normalized_user_id,
            "target_email": normalized_email,
            "code": code,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hmac.new(
        pepper_bytes,
        message,
        hashlib.sha256,
    ).hexdigest()


def verify_email_otp_code(
    *,
    code: str,
    expected_digest: str,
    otp_pepper: str,
    purpose: str,
    user_id: str,
    target_email: str,
) -> bool:
    try:
        candidate_digest = hash_email_otp_code(
            code=code,
            otp_pepper=otp_pepper,
            purpose=purpose,
            user_id=user_id,
            target_email=target_email,
        )
    except ValueError:
        return False

    return hmac.compare_digest(candidate_digest, expected_digest)


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
