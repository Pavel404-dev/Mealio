import uuid

import pytest

from app.core.auth_abuse import AuthAbuseDimension
from app.core.security import (
    hash_auth_abuse_identifier,
    normalize_auth_abuse_identifier,
)


ABUSE_PEPPER = "test-auth-abuse-pepper-with-at-least-32-characters"


def test_auth_abuse_digest_is_deterministic_and_pseudonymous() -> None:
    raw_email = "private-user@example.com"

    first_digest = hash_auth_abuse_identifier(
        dimension=AuthAbuseDimension.EMAIL,
        identifier=raw_email,
        abuse_pepper=ABUSE_PEPPER,
    )
    second_digest = hash_auth_abuse_identifier(
        dimension=AuthAbuseDimension.EMAIL,
        identifier=raw_email,
        abuse_pepper=ABUSE_PEPPER,
    )

    assert first_digest == second_digest
    assert len(first_digest) == 64
    assert raw_email not in first_digest


def test_auth_abuse_digest_normalizes_email() -> None:
    first_digest = hash_auth_abuse_identifier(
        dimension=AuthAbuseDimension.EMAIL,
        identifier="  User@Example.COM  ",
        abuse_pepper=ABUSE_PEPPER,
    )
    second_digest = hash_auth_abuse_identifier(
        dimension=AuthAbuseDimension.EMAIL,
        identifier="user@example.com",
        abuse_pepper=ABUSE_PEPPER,
    )

    assert first_digest == second_digest


def test_auth_abuse_digest_normalizes_ip_addresses() -> None:
    expanded = hash_auth_abuse_identifier(
        dimension=AuthAbuseDimension.IP,
        identifier="2001:0db8:0000:0000:0000:0000:0000:0001",
        abuse_pepper=ABUSE_PEPPER,
    )
    compressed = hash_auth_abuse_identifier(
        dimension=AuthAbuseDimension.IP,
        identifier="2001:db8::1",
        abuse_pepper=ABUSE_PEPPER,
    )
    mapped = normalize_auth_abuse_identifier(
        dimension=AuthAbuseDimension.IP,
        identifier="::ffff:192.0.2.10",
    )

    assert expanded == compressed
    assert mapped == "192.0.2.10"


def test_auth_abuse_digest_normalizes_user_uuid() -> None:
    user_id = uuid.uuid4()

    normalized = normalize_auth_abuse_identifier(
        dimension=AuthAbuseDimension.USER,
        identifier=f"  {str(user_id).upper()}  ",
    )

    assert normalized == str(user_id)


def test_auth_abuse_digest_is_bound_to_dimension() -> None:
    email_digest = hash_auth_abuse_identifier(
        dimension=AuthAbuseDimension.EMAIL,
        identifier="192.0.2.10",
        abuse_pepper=ABUSE_PEPPER,
    )
    ip_digest = hash_auth_abuse_identifier(
        dimension=AuthAbuseDimension.IP,
        identifier="192.0.2.10",
        abuse_pepper=ABUSE_PEPPER,
    )

    assert email_digest != ip_digest


def test_auth_abuse_digest_rejects_invalid_identifiers() -> None:
    with pytest.raises(ValueError, match="IP identifier is invalid"):
        normalize_auth_abuse_identifier(
            dimension=AuthAbuseDimension.IP,
            identifier="not-an-ip",
        )

    with pytest.raises(ValueError, match="user identifier is invalid"):
        normalize_auth_abuse_identifier(
            dimension=AuthAbuseDimension.USER,
            identifier="not-a-uuid",
        )

    with pytest.raises(ValueError, match="identifier is required"):
        normalize_auth_abuse_identifier(
            dimension=AuthAbuseDimension.EMAIL,
            identifier="   ",
        )


def test_auth_abuse_digest_rejects_short_pepper() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        hash_auth_abuse_identifier(
            dimension=AuthAbuseDimension.EMAIL,
            identifier="user@example.com",
            abuse_pepper="too-short",
        )
