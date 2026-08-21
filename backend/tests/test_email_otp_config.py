import pytest
from pydantic import ValidationError

from app.core.config import Settings

DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/mealio_test"
JWT_SECRET = "test-jwt-secret-key-with-at-least-32-characters"
OTP_PEPPER = "test-email-otp-pepper-with-at-least-32-characters"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": DATABASE_URL,
        "jwt_secret_key": JWT_SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_email_otp_config_defaults() -> None:
    settings = _settings()

    assert settings.email_otp_pepper is None
    assert settings.email_otp_expire_minutes == 10
    assert settings.email_otp_max_attempts == 5
    assert settings.email_otp_resend_cooldown_seconds == 60
    assert settings.email_otp_max_deliveries_per_window == 5


def test_email_otp_config_accepts_valid_pepper() -> None:
    settings = _settings(email_otp_pepper=OTP_PEPPER)

    assert settings.email_otp_pepper is not None
    assert settings.email_otp_pepper.get_secret_value() == OTP_PEPPER


def test_email_otp_config_treats_blank_pepper_as_unconfigured() -> None:
    settings = _settings(email_otp_pepper="   ")

    assert settings.email_otp_pepper is None


def test_email_otp_config_rejects_short_pepper() -> None:
    with pytest.raises(ValidationError):
        _settings(email_otp_pepper="x" * 31)


def test_email_otp_config_rejects_jwt_secret_reuse() -> None:
    with pytest.raises(ValidationError, match="different from JWT_SECRET_KEY"):
        _settings(email_otp_pepper=JWT_SECRET)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("email_otp_expire_minutes", 0),
        ("email_otp_expire_minutes", 31),
        ("email_otp_max_attempts", 0),
        ("email_otp_max_attempts", 11),
        ("email_otp_resend_cooldown_seconds", 0),
        ("email_otp_resend_cooldown_seconds", 3601),
        ("email_otp_max_deliveries_per_window", 0),
        ("email_otp_max_deliveries_per_window", 21),
    ],
)
def test_email_otp_config_rejects_invalid_numeric_boundaries(
    field_name: str,
    invalid_value: int,
) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field_name: invalid_value})
