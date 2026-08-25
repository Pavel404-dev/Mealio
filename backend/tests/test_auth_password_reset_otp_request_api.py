from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_password_reset_otp_mailer
from app.core.config import get_settings
from app.main import app
from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose

REGISTER_URL = "/api/v1/auth/register"
OTP_REQUEST_URL = "/api/v1/auth/password-reset/otp/request"
GENERIC_MESSAGE = (
    "If an account with that email exists, a password reset code has been sent."
)
PASSWORD = "Mealio-password-123"


class FakePasswordResetOtpMailer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, datetime]] = []

    def send_password_reset_otp(
        self,
        *,
        recipient_email: str,
        reset_code: SecretStr,
        expires_at: datetime,
    ) -> None:
        self.calls.append(
            (
                recipient_email,
                reset_code.get_secret_value(),
                expires_at,
            )
        )


def _use_fake_mailer(mailer: FakePasswordResetOtpMailer) -> None:
    app.dependency_overrides[get_password_reset_otp_mailer] = lambda: mailer


async def _register_user(client: AsyncClient, *, email: str) -> dict:
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "OTP Password Reset User",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_otp_reset_request_is_generic_and_stores_only_password_reset_digest(
    client: AsyncClient,
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mailer = FakePasswordResetOtpMailer()
    _use_fake_mailer(mailer)
    registered_user = await _register_user(
        client,
        email="otp-reset-request@example.com",
    )

    known_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "  OTP-RESET-REQUEST@EXAMPLE.COM  "},
    )
    unknown_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "unknown-otp-reset@example.com"},
    )

    assert known_response.status_code == 202
    assert unknown_response.status_code == 202
    assert (
        known_response.json() == unknown_response.json() == {"message": GENERIC_MESSAGE}
    )
    assert len(mailer.calls) == 1

    recipient, raw_code, expires_at = mailer.calls[0]
    assert recipient == "otp-reset-request@example.com"
    assert len(raw_code) == 6
    assert raw_code.isascii()
    assert raw_code.isdigit()
    assert expires_at > datetime.now(UTC)
    assert raw_code not in known_response.text
    assert raw_code not in caplog.text

    result = await db_session.execute(select(EmailOtpChallenge))
    challenge = result.scalar_one()
    assert str(challenge.user_id) == registered_user["id"]
    assert challenge.purpose is EmailOtpPurpose.PASSWORD_RESET
    assert challenge.target_email == "otp-reset-request@example.com"
    assert challenge.code_digest != raw_code
    assert raw_code not in challenge.code_digest


@pytest.mark.asyncio
async def test_otp_reset_request_cooldown_is_generic_and_skips_delivery(
    client: AsyncClient,
) -> None:
    mailer = FakePasswordResetOtpMailer()
    _use_fake_mailer(mailer)
    await _register_user(client, email="otp-reset-cooldown@example.com")

    first = await client.post(
        OTP_REQUEST_URL,
        json={"email": "otp-reset-cooldown@example.com"},
    )
    second = await client.post(
        OTP_REQUEST_URL,
        json={"email": "otp-reset-cooldown@example.com"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == second.json() == {"message": GENERIC_MESSAGE}
    assert len(mailer.calls) == 1


@pytest.mark.asyncio
async def test_otp_reset_request_configuration_failure_is_account_agnostic(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mailer = FakePasswordResetOtpMailer()
    _use_fake_mailer(mailer)
    await _register_user(client, email="otp-reset-config@example.com")
    monkeypatch.setattr(get_settings(), "email_otp_pepper", None)

    known_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "otp-reset-config@example.com"},
    )
    unknown_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "unknown-otp-reset-config@example.com"},
    )

    expected = {"detail": "Password reset code is not configured"}
    assert known_response.status_code == 503
    assert unknown_response.status_code == 503
    assert known_response.json() == unknown_response.json() == expected
    assert mailer.calls == []
    assert await db_session.scalar(select(func.count(EmailOtpChallenge.id))) == 0


@pytest.mark.asyncio
async def test_otp_reset_request_smtp_configuration_failure_is_account_agnostic(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register_user(client, email="otp-reset-smtp-config@example.com")
    app.dependency_overrides.pop(get_password_reset_otp_mailer)
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_from_email", None)

    known_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "otp-reset-smtp-config@example.com"},
    )
    unknown_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "unknown-otp-reset-smtp-config@example.com"},
    )

    expected = {"detail": "Password reset code delivery is not configured"}
    assert known_response.status_code == 503
    assert unknown_response.status_code == 503
    assert known_response.json() == unknown_response.json() == expected
    assert await db_session.scalar(select(func.count(EmailOtpChallenge.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": None},
        {"email": ""},
        {"email": "not-an-email"},
    ],
)
async def test_otp_reset_request_rejects_invalid_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    mailer = FakePasswordResetOtpMailer()
    _use_fake_mailer(mailer)

    response = await client.post(OTP_REQUEST_URL, json=payload)

    assert response.status_code == 422
    assert mailer.calls == []
