from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr

from app.integrations.smtp_password_reset_mailer import SmtpPasswordResetMailer


def test_smtp_mailer_builds_reset_link_without_logging_or_returning_token() -> None:
    mailer = SmtpPasswordResetMailer(
        host="smtp.example.com",
        port=587,
        username=None,
        password=None,
        from_email="noreply@example.com",
        starttls=True,
        reset_url_base="https://app.example.com/reset-password?source=email&token=old",
    )

    reset_url = mailer._build_reset_url("new-sensitive-token")
    parts = urlsplit(reset_url)
    query = parse_qs(parts.query)

    assert parts.scheme == "https"
    assert parts.netloc == "app.example.com"
    assert parts.path == "/reset-password"
    assert query["source"] == ["email"]
    assert query["token"] == ["new-sensitive-token"]


@pytest.mark.parametrize(
    "url",
    [
        "",
        "reset-password",
        "ftp://example.com/reset-password",
        "https:///reset-password",
    ],
)
def test_smtp_mailer_rejects_invalid_reset_url_base(url: str) -> None:
    with pytest.raises(ValueError, match="absolute HTTP\\(S\\) URL"):
        SmtpPasswordResetMailer(
            host="smtp.example.com",
            port=587,
            username=None,
            password=None,
            from_email="noreply@example.com",
            starttls=True,
            reset_url_base=url,
        )


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


def test_smtp_mailer_sends_message_with_tls_and_credentials(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.integrations.smtp_password_reset_mailer.smtplib.SMTP",
        FakeSMTP,
    )
    mailer = SmtpPasswordResetMailer(
        host="smtp.example.com",
        port=587,
        username="mailer-user",
        password="mailer-password",
        from_email="noreply@example.com",
        starttls=True,
        reset_url_base="https://app.example.com/reset-password",
    )

    mailer.send_password_reset(
        recipient_email="user@example.com",
        reset_token=SecretStr("sensitive-reset-token"),
    )

    smtp = FakeSMTP.instance
    assert smtp is not None
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.started_tls is True
    assert smtp.logged_in_with == ("mailer-user", "mailer-password")
    assert smtp.message["From"] == "noreply@example.com"
    assert smtp.message["To"] == "user@example.com"
    assert "sensitive-reset-token" in smtp.message.get_content()
