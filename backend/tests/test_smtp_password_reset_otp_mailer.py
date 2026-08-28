import smtplib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from app.integrations.password_reset_otp_mailer import PasswordResetOtpDeliveryError
from app.integrations.smtp_password_reset_otp_mailer import SmtpPasswordResetOtpMailer


class FakeSMTP:
    instance = None

    def __init__(self, host: str, port: int, *, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in_with: tuple[str, str] | None = None
        self.message = None
        FakeSMTP.instance = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self, *, context) -> None:
        assert context is not None
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in_with = (username, password)

    def send_message(self, message) -> None:
        self.message = message


def test_smtp_password_reset_otp_mailer_preserves_code_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.integrations.smtp_password_reset_otp_mailer.smtplib.SMTP",
        FakeSMTP,
    )
    mailer = SmtpPasswordResetOtpMailer(
        host="smtp.example.com",
        port=587,
        username="mailer-user",
        password="mailer-password",
        from_email="noreply@example.com",
        starttls=True,
    )
    code = "001234"
    secret_code = SecretStr(code)
    expires_at = datetime.now(UTC) + timedelta(minutes=10)

    mailer.send_password_reset_otp(
        recipient_email="user@example.com",
        reset_code=secret_code,
        expires_at=expires_at,
    )

    smtp = FakeSMTP.instance
    assert smtp is not None
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.timeout == 10
    assert smtp.started_tls is True
    assert smtp.logged_in_with == ("mailer-user", "mailer-password")
    assert smtp.message["From"] == "noreply@example.com"
    assert smtp.message["To"] == "user@example.com"
    assert code not in smtp.message["Subject"]
    assert code in smtp.message.get_content()
    assert "expires" in smtp.message.get_content()
    assert "ignore" in smtp.message.get_content()
    assert code not in str(secret_code)
    assert code not in repr(secret_code)


def test_smtp_password_reset_otp_mailer_supports_mailpit_without_auth_or_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.integrations.smtp_password_reset_otp_mailer.smtplib.SMTP",
        FakeSMTP,
    )
    mailer = SmtpPasswordResetOtpMailer(
        host="mailpit",
        port=1025,
        username=None,
        password=None,
        from_email="noreply@example.com",
        starttls=False,
    )

    mailer.send_password_reset_otp(
        recipient_email="user@example.com",
        reset_code=SecretStr("123456"),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    smtp = FakeSMTP.instance
    assert smtp is not None
    assert smtp.started_tls is False
    assert smtp.logged_in_with is None


class FailingSMTP(FakeSMTP):
    def send_message(self, message) -> None:
        raise smtplib.SMTPException(
            "server rejected sensitive-code-654321 with mailer-password"
        )


def test_smtp_password_reset_otp_failure_is_generic_and_secret_free(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        "app.integrations.smtp_password_reset_otp_mailer.smtplib.SMTP",
        FailingSMTP,
    )
    mailer = SmtpPasswordResetOtpMailer(
        host="smtp.example.com",
        port=587,
        username="mailer-user",
        password="mailer-password",
        from_email="noreply@example.com",
        starttls=True,
    )

    with pytest.raises(PasswordResetOtpDeliveryError) as exc_info:
        mailer.send_password_reset_otp(
            recipient_email="private-user@example.com",
            reset_code=SecretStr("654321"),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )

    public_error = str(exc_info.value)
    assert public_error == "Password reset code delivery failed"
    for secret in ("654321", "mailer-password", "private-user@example.com"):
        assert secret not in public_error
        assert secret not in caplog.text


def test_smtp_password_reset_otp_mailer_rejects_naive_expiration() -> None:
    mailer = SmtpPasswordResetOtpMailer(
        host="smtp.example.com",
        port=587,
        username=None,
        password=None,
        from_email="noreply@example.com",
        starttls=False,
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        mailer.send_password_reset_otp(
            recipient_email="user@example.com",
            reset_code=SecretStr("123456"),
            expires_at=datetime.now(),
        )
