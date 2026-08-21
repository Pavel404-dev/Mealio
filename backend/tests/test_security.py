import pytest

from app.core.security import (
    generate_email_otp_code,
    hash_email_otp_code,
    hash_password,
    verify_email_otp_code,
    verify_password,
)

OTP_PEPPER = "test-email-otp-pepper-with-at-least-32-characters"


def test_hash_password_does_not_return_plaintext() -> None:
    plain_password = "Mealio-secure-password"

    hashed_password = hash_password(plain_password)

    assert hashed_password != plain_password


def test_hash_password_uses_argon2_format() -> None:
    hashed_password = hash_password("Mealio-secure-password")

    assert hashed_password.startswith("$argon2id$")
    assert len(hashed_password) <= 255


def test_verify_password_accepts_correct_password() -> None:
    plain_password = "Mealio-secure-password"
    hashed_password = hash_password(plain_password)

    assert verify_password(plain_password, hashed_password) is True


def test_verify_password_rejects_incorrect_password() -> None:
    hashed_password = hash_password("correct-password")

    assert (
        verify_password(
            "incorrect-password",
            hashed_password,
        )
        is False
    )


def test_hash_password_uses_random_salt() -> None:
    plain_password = "Mealio-secure-password"

    first_hash = hash_password(plain_password)
    second_hash = hash_password(plain_password)

    assert first_hash != second_hash


def test_both_hashes_verify_for_same_password() -> None:
    plain_password = "Mealio-secure-password"

    first_hash = hash_password(plain_password)
    second_hash = hash_password(plain_password)

    assert verify_password(plain_password, first_hash) is True
    assert verify_password(plain_password, second_hash) is True


def test_verify_password_rejects_invalid_or_unknown_hash() -> None:
    plain_password = "Mealio-secure-password"

    assert (
        verify_password(
            plain_password,
            "not-a-valid-password-hash",
        )
        is False
    )

    assert (
        verify_password(
            plain_password,
            "$argon2id$v=19$m=65536,t=3,p=4$invalid",
        )
        is False
    )


def test_unicode_password_can_be_hashed_and_verified() -> None:
    plain_password = "Mealio-Пароль-🔐"

    hashed_password = hash_password(plain_password)

    assert verify_password(plain_password, hashed_password) is True


def test_unicode_password_rejects_different_value() -> None:
    plain_password = "Mealio-Пароль-🔐"
    different_password = "Mealio-Пароль-🔓"

    hashed_password = hash_password(plain_password)

    assert (
        verify_password(
            different_password,
            hashed_password,
        )
        is False
    )


def test_verify_password_rejects_missing_hash() -> None:
    assert verify_password("Mealio-secure-password", None) is False
    assert verify_password("Mealio-secure-password", "") is False


def test_generate_email_otp_code_has_exactly_six_ascii_digits() -> None:
    for _ in range(100):
        code = generate_email_otp_code()

        assert len(code) == 6
        assert code.isascii()
        assert code.isdigit()


def test_generate_email_otp_code_preserves_leading_zeroes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.security.secrets.randbelow",
        lambda _: 42,
    )

    assert generate_email_otp_code() == "000042"


def test_hash_email_otp_code_is_deterministic() -> None:
    first_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email="user@example.com",
    )
    second_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email="user@example.com",
    )

    assert first_digest == second_digest
    assert len(first_digest) == 64


def test_email_otp_digest_changes_with_code() -> None:
    first_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email="user@example.com",
    )
    second_digest = hash_email_otp_code(
        code="654321",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email="user@example.com",
    )

    assert first_digest != second_digest


def test_hash_email_otp_code_normalizes_email() -> None:
    first_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email=" User@Example.COM ",
    )
    second_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email="user@example.com",
    )

    assert first_digest == second_digest


def test_email_otp_digest_is_bound_to_purpose() -> None:
    verification_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email="user@example.com",
    )
    reset_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="password_reset",
        user_id="user-123",
        target_email="user@example.com",
    )

    assert verification_digest != reset_digest


def test_email_otp_digest_is_bound_to_user() -> None:
    first_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email="user@example.com",
    )
    second_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-456",
        target_email="user@example.com",
    )

    assert first_digest != second_digest


def test_email_otp_digest_is_bound_to_email() -> None:
    first_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email="first@example.com",
    )
    second_digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="email_verification",
        user_id="user-123",
        target_email="second@example.com",
    )

    assert first_digest != second_digest


def test_hash_email_otp_code_rejects_non_ascii_digits() -> None:
    with pytest.raises(ValueError, match="6 ASCII digits"):
        hash_email_otp_code(
            code="１２３４５６",
            otp_pepper=OTP_PEPPER,
            purpose="email_verification",
            user_id="user-123",
            target_email="user@example.com",
        )


def test_hash_email_otp_code_rejects_short_pepper() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        hash_email_otp_code(
            code="123456",
            otp_pepper="too-short",
            purpose="email_verification",
            user_id="user-123",
            target_email="user@example.com",
        )


def test_verify_email_otp_code_accepts_correct_code() -> None:
    digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="password_reset",
        user_id="user-123",
        target_email="user@example.com",
    )

    assert (
        verify_email_otp_code(
            code="123456",
            expected_digest=digest,
            otp_pepper=OTP_PEPPER,
            purpose="password_reset",
            user_id="user-123",
            target_email="user@example.com",
        )
        is True
    )


def test_verify_email_otp_code_rejects_wrong_code() -> None:
    digest = hash_email_otp_code(
        code="123456",
        otp_pepper=OTP_PEPPER,
        purpose="password_reset",
        user_id="user-123",
        target_email="user@example.com",
    )

    assert (
        verify_email_otp_code(
            code="654321",
            expected_digest=digest,
            otp_pepper=OTP_PEPPER,
            purpose="password_reset",
            user_id="user-123",
            target_email="user@example.com",
        )
        is False
    )


def test_verify_email_otp_code_rejects_invalid_format() -> None:
    assert (
        verify_email_otp_code(
            code="12345",
            expected_digest="0" * 64,
            otp_pepper=OTP_PEPPER,
            purpose="password_reset",
            user_id="user-123",
            target_email="user@example.com",
        )
        is False
    )
