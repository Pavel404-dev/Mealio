from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.email_verification_otp_mailer import (
    EmailVerificationOtpDeliveryError,
)
from app.integrations.mailtrap_api_mailer import MailtrapApiMailer
from app.integrations.password_reset_otp_mailer import (
    PasswordResetOtpDeliveryError,
)


def _mailer() -> MailtrapApiMailer:
    return MailtrapApiMailer(
        api_token="test-api-token",
        sandbox_id=4912297,
        from_email="no-reply@example.com",
        verification_url_base="https://staging.example.com/verify-email",
        reset_url_base="https://staging.example.com/reset-password",
    )


def test_mailtrap_api_mailer_sends_verification_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={"success": True, "message_ids": ["message-id"]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.integrations.mailtrap_api_mailer.httpx.post", fake_post)

    _mailer().send_email_verification(
        recipient_email="person@example.com",
        verification_token=SecretStr("verification-secret"),
    )

    assert captured["url"] == ("https://sandbox.api.mailtrap.io/api/send/4912297")
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Api-Token"] == "test-api-token"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["to"] == [{"email": "person@example.com"}]
    assert "verification-secret" in str(payload["text"])
    assert "test-api-token" not in str(payload)


def test_mailtrap_api_mailer_sends_verification_otp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={"success": True, "message_ids": ["message-id"]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.integrations.mailtrap_api_mailer.httpx.post", fake_post)

    _mailer().send_email_verification_otp(
        recipient_email="person@example.com",
        verification_code=SecretStr("123456"),
        expires_at=datetime(2026, 9, 16, 14, 30, tzinfo=UTC),
    )

    payload = captured["json"]
    assert isinstance(payload, dict)
    assert "123456" in str(payload["text"])
    assert "2026-09-16 14:30 UTC" in str(payload["text"])


def test_mailtrap_api_mailer_rejects_naive_otp_expiration() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _mailer().send_email_verification_otp(
            recipient_email="person@example.com",
            verification_code=SecretStr("123456"),
            expires_at=datetime(2026, 9, 16, 14, 30),
        )


@pytest.mark.parametrize(
    ("method_name", "error_type", "secret_name"),
    [
        (
            "send_email_verification_otp",
            EmailVerificationOtpDeliveryError,
            "verification_code",
        ),
        (
            "send_password_reset_otp",
            PasswordResetOtpDeliveryError,
            "reset_code",
        ),
    ],
)
def test_mailtrap_api_mailer_maps_otp_delivery_errors(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    error_type: type[RuntimeError],
    secret_name: str,
) -> None:
    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        return httpx.Response(
            401,
            json={"success": False, "errors": ["Unauthorized"]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.integrations.mailtrap_api_mailer.httpx.post", fake_post)
    method = getattr(_mailer(), method_name)

    with pytest.raises(error_type) as exc_info:
        method(
            recipient_email="person@example.com",
            **{
                secret_name: SecretStr("123456"),
                "expires_at": datetime(2026, 9, 16, 14, 30, tzinfo=UTC),
            },
        )

    assert "test-api-token" not in str(exc_info.value)
