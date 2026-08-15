import string

import pytest
from pydantic import SecretStr, ValidationError

from app.core.security import (
    generate_password_reset_token,
    hash_password_reset_token,
)
from app.schemas.auth import PasswordResetConfirm, PasswordResetRequest

_HEX_DIGITS = set(string.hexdigits.lower())


def test_generate_password_reset_token_returns_high_entropy_opaque_value() -> None:
    first_token = generate_password_reset_token()
    second_token = generate_password_reset_token()

    assert isinstance(first_token, str)
    assert len(first_token) >= 43
    assert first_token != second_token
    assert "." not in first_token


def test_hash_password_reset_token_is_deterministic_sha256_hex_digest() -> None:
    reset_token = generate_password_reset_token()

    first_hash = hash_password_reset_token(reset_token)
    second_hash = hash_password_reset_token(reset_token)

    assert first_hash == second_hash
    assert first_hash != reset_token
    assert len(first_hash) == 64
    assert set(first_hash) <= _HEX_DIGITS


def test_different_password_reset_tokens_have_different_hashes() -> None:
    first_token = generate_password_reset_token()
    second_token = generate_password_reset_token()

    assert hash_password_reset_token(first_token) != hash_password_reset_token(
        second_token
    )


def test_password_reset_confirm_masks_token_and_password() -> None:
    raw_token = generate_password_reset_token()
    raw_password = "Sensitive-new-password-123"
    request = PasswordResetConfirm(
        token=raw_token,
        new_password=raw_password,
    )

    assert isinstance(request.token, SecretStr)
    assert isinstance(request.new_password, SecretStr)
    assert request.token.get_secret_value() == raw_token
    assert request.new_password.get_secret_value() == raw_password
    assert raw_token not in repr(request)
    assert raw_password not in repr(request)
    assert raw_token not in request.model_dump_json()
    assert raw_password not in request.model_dump_json()


def test_password_reset_validation_error_does_not_expose_raw_token() -> None:
    oversized_token = "sensitive-reset-token-" + ("x" * 600)

    with pytest.raises(ValidationError) as exc_info:
        PasswordResetConfirm(
            token=oversized_token,
            new_password="Sensitive-new-password-123",
        )

    assert oversized_token not in str(exc_info.value)


def test_password_reset_request_normalizes_email() -> None:
    request = PasswordResetRequest(email="  Pavel.User@Example.COM  ")

    assert str(request.email) == "pavel.user@example.com"
