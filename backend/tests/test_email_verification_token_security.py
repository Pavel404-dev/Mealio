import string

import pytest
from pydantic import SecretStr, ValidationError

from app.core.security import (
    generate_email_verification_token,
    hash_email_verification_token,
)
from app.schemas.auth import EmailVerificationConfirm, EmailVerificationRequest

_HEX_DIGITS = set(string.hexdigits.lower())


def test_generate_email_verification_token_returns_high_entropy_opaque_value() -> None:
    first_token = generate_email_verification_token()
    second_token = generate_email_verification_token()

    assert isinstance(first_token, str)
    assert len(first_token) >= 43
    assert first_token != second_token
    assert "." not in first_token


def test_hash_email_verification_token_is_deterministic_sha256_hex_digest() -> None:
    verification_token = generate_email_verification_token()

    first_hash = hash_email_verification_token(verification_token)
    second_hash = hash_email_verification_token(verification_token)

    assert first_hash == second_hash
    assert first_hash != verification_token
    assert len(first_hash) == 64
    assert set(first_hash) <= _HEX_DIGITS


def test_different_email_verification_tokens_have_different_hashes() -> None:
    first_token = generate_email_verification_token()
    second_token = generate_email_verification_token()

    assert hash_email_verification_token(first_token) != hash_email_verification_token(
        second_token
    )


def test_email_verification_confirm_masks_token() -> None:
    raw_token = generate_email_verification_token()
    request = EmailVerificationConfirm(token=raw_token)

    assert isinstance(request.token, SecretStr)
    assert request.token.get_secret_value() == raw_token
    assert raw_token not in repr(request)
    assert raw_token not in request.model_dump_json()


def test_email_verification_validation_error_does_not_expose_raw_token() -> None:
    oversized_token = "sensitive-verification-token-" + ("x" * 600)

    with pytest.raises(ValidationError) as exc_info:
        EmailVerificationConfirm(token=oversized_token)

    assert oversized_token not in str(exc_info.value)


def test_email_verification_request_normalizes_email() -> None:
    request = EmailVerificationRequest(email="  Pavel.User@Example.COM  ")

    assert str(request.email) == "pavel.user@example.com"
