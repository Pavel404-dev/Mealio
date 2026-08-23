from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_email_verification_otp_mailer
from app.main import app
from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose
from app.models.user import User

REGISTER_URL = "/api/v1/auth/register"
OTP_REQUEST_URL = "/api/v1/auth/email-verification/otp/request"
GENERIC_MESSAGE = (
    "If verification is needed for that email, a verification code has been sent."
)
PASSWORD = "Mealio-password-123"


class FakeEmailVerificationOtpMailer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, datetime]] = []

    def send_email_verification_otp(
        self,
        *,
        recipient_email: str,
        verification_code: SecretStr,
        expires_at: datetime,
    ) -> None:
        self.calls.append(
            (
                recipient_email,
                verification_code.get_secret_value(),
                expires_at,
            )
        )


def _use_fake_mailer(mailer: FakeEmailVerificationOtpMailer) -> None:
    app.dependency_overrides[get_email_verification_otp_mailer] = lambda: mailer


async def _register_user(client: AsyncClient, *, email: str) -> dict:
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "OTP Request User",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_otp_request_has_same_contract_for_all_account_states(
    client: AsyncClient,
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)
    await _register_user(client, email="otp-request@example.com")

    unverified_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "  OTP-REQUEST@EXAMPLE.COM  "},
    )

    assert unverified_response.status_code == 202
    assert unverified_response.json() == {"message": GENERIC_MESSAGE}
    assert len(mailer.calls) == 1

    recipient, raw_code, expires_at = mailer.calls[0]
    assert recipient == "otp-request@example.com"
    assert len(raw_code) == 6
    assert raw_code.isascii()
    assert raw_code.isdigit()
    assert expires_at > datetime.now(UTC)
    assert raw_code not in unverified_response.text
    assert raw_code not in caplog.text

    async with db_session.begin():
        challenge_result = await db_session.execute(
            select(EmailOtpChallenge).where(
                EmailOtpChallenge.target_email == "otp-request@example.com"
            )
        )
        challenge = challenge_result.scalar_one()
        user_result = await db_session.execute(
            select(User).where(User.email == "otp-request@example.com")
        )
        user = user_result.scalar_one()
        user.email_verified_at = datetime.now(UTC)

    assert challenge.purpose is EmailOtpPurpose.EMAIL_VERIFICATION
    assert challenge.code_digest != raw_code
    assert raw_code not in challenge.code_digest

    verified_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "otp-request@example.com"},
    )
    unknown_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "unknown-otp@example.com"},
    )

    assert verified_response.status_code == 202
    assert unknown_response.status_code == 202
    assert verified_response.json() == unknown_response.json()
    assert verified_response.json() == unverified_response.json()
    assert len(mailer.calls) == 1

    challenge_count = await db_session.scalar(select(func.count(EmailOtpChallenge.id)))
    assert challenge_count == 1


@pytest.mark.asyncio
async def test_otp_request_cooldown_keeps_generic_response_and_skips_delivery(
    client: AsyncClient,
) -> None:
    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)
    await _register_user(client, email="otp-cooldown-api@example.com")

    first = await client.post(
        OTP_REQUEST_URL,
        json={"email": "otp-cooldown-api@example.com"},
    )
    second = await client.post(
        OTP_REQUEST_URL,
        json={"email": "otp-cooldown-api@example.com"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == second.json() == {"message": GENERIC_MESSAGE}
    assert len(mailer.calls) == 1


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
async def test_otp_request_rejects_invalid_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)

    response = await client.post(OTP_REQUEST_URL, json=payload)

    assert response.status_code == 422
    assert mailer.calls == []
