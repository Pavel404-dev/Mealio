import pytest
from pydantic import ValidationError

from app.core.auth_abuse import (
    AuthAbuseAction,
    AuthAbuseDimension,
    default_auth_abuse_policies,
)
from app.core.config import Settings


DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/mealio_test"
JWT_SECRET = "test-jwt-secret-key-with-at-least-32-characters"
OTP_PEPPER = "test-email-otp-pepper-with-at-least-32-characters"
ABUSE_PEPPER = "test-auth-abuse-pepper-with-at-least-32-characters"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": DATABASE_URL,
        "jwt_secret_key": JWT_SECRET,
        "auth_abuse_pepper": ABUSE_PEPPER,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_auth_abuse_config_defaults() -> None:
    settings = _settings()
    policies = {
        (policy.action, policy.dimension): (
            policy.limit,
            policy.window_seconds,
        )
        for policy in settings.auth_abuse_policies
    }

    assert settings.auth_abuse_pepper.get_secret_value() == ABUSE_PEPPER
    assert policies[(AuthAbuseAction.LOGIN, AuthAbuseDimension.IP)] == (30, 300)
    assert policies[(AuthAbuseAction.LOGIN, AuthAbuseDimension.EMAIL)] == (10, 900)
    assert policies[
        (AuthAbuseAction.PASSWORD_RESET_REQUEST, AuthAbuseDimension.EMAIL)
    ] == (3, 3600)
    assert policies[
        (AuthAbuseAction.EMAIL_VERIFICATION_CONFIRM, AuthAbuseDimension.IP)
    ] == (30, 300)


def test_auth_abuse_config_rejects_missing_pepper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTH_ABUSE_PEPPER", raising=False)

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            jwt_secret_key=JWT_SECRET,
        )


def test_auth_abuse_config_rejects_blank_pepper() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        _settings(auth_abuse_pepper="   ")


def test_auth_abuse_config_rejects_short_pepper() -> None:
    with pytest.raises(ValidationError):
        _settings(auth_abuse_pepper="x" * 31)


def test_auth_abuse_config_rejects_jwt_secret_reuse() -> None:
    with pytest.raises(ValidationError, match="different from JWT_SECRET_KEY"):
        _settings(auth_abuse_pepper=JWT_SECRET)


def test_auth_abuse_config_rejects_email_otp_pepper_reuse() -> None:
    with pytest.raises(ValidationError, match="different from EMAIL_OTP_PEPPER"):
        _settings(
            email_otp_pepper=OTP_PEPPER,
            auth_abuse_pepper=OTP_PEPPER,
        )


def test_auth_abuse_config_rejects_duplicate_policy() -> None:
    policies = default_auth_abuse_policies()
    policies.append(policies[0])

    with pytest.raises(ValidationError, match="duplicate action/dimension"):
        _settings(auth_abuse_policies=policies)


def test_auth_abuse_config_rejects_missing_required_policy() -> None:
    policies = default_auth_abuse_policies()[1:]

    with pytest.raises(ValidationError, match="missing required policies"):
        _settings(auth_abuse_policies=policies)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("limit", 0),
        ("limit", 10_001),
        ("window_seconds", 0),
        ("window_seconds", 86_401),
    ],
)
def test_auth_abuse_config_rejects_policy_boundaries(
    field_name: str,
    invalid_value: int,
) -> None:
    policies = [policy.model_dump() for policy in default_auth_abuse_policies()]
    policies[0][field_name] = invalid_value

    with pytest.raises(ValidationError):
        _settings(auth_abuse_policies=policies)
