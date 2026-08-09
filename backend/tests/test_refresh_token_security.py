import string

import pytest
from pydantic import SecretStr, ValidationError

from app.core.security import generate_refresh_token, hash_refresh_token
from app.schemas.auth import RefreshTokenRequest, TokenPairResponse


_HEX_DIGITS = set(string.hexdigits.lower())


def test_generate_refresh_token_returns_high_entropy_opaque_value() -> None:
    first_token = generate_refresh_token()
    second_token = generate_refresh_token()

    assert isinstance(first_token, str)
    assert len(first_token) >= 43
    assert first_token != second_token
    assert "." not in first_token


def test_hash_refresh_token_is_deterministic_sha256_hex_digest() -> None:
    refresh_token = generate_refresh_token()

    first_hash = hash_refresh_token(refresh_token)
    second_hash = hash_refresh_token(refresh_token)

    assert first_hash == second_hash
    assert first_hash != refresh_token
    assert len(first_hash) == 64
    assert set(first_hash) <= _HEX_DIGITS


def test_different_refresh_tokens_have_different_hashes() -> None:
    first_token = generate_refresh_token()
    second_token = generate_refresh_token()

    assert hash_refresh_token(first_token) != hash_refresh_token(second_token)


def test_refresh_token_request_uses_secret_str_and_masks_value() -> None:
    raw_refresh_token = generate_refresh_token()
    request = RefreshTokenRequest(refresh_token=raw_refresh_token)

    assert isinstance(request.refresh_token, SecretStr)
    assert request.refresh_token.get_secret_value() == raw_refresh_token
    assert raw_refresh_token not in repr(request)
    assert raw_refresh_token not in str(request)
    assert raw_refresh_token not in request.model_dump_json()


def test_refresh_token_validation_error_does_not_expose_raw_value() -> None:
    oversized_refresh_token = "sensitive-refresh-token-" + ("x" * 600)

    with pytest.raises(ValidationError) as exc_info:
        RefreshTokenRequest(
            refresh_token=oversized_refresh_token,
        )

    assert oversized_refresh_token not in str(exc_info.value)


def test_token_pair_response_exposes_only_required_token_fields() -> None:
    response = TokenPairResponse(
        access_token="access-token",
        refresh_token="refresh-token",
    )

    data = response.model_dump()

    assert data == {
        "access_token": "access-token",
        "token_type": "bearer",
        "refresh_token": "refresh-token",
    }
    assert "password" not in data
    assert "password_hash" not in data
