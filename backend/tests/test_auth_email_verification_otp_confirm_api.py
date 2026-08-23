import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_email_verification_otp_mailer
from app.main import app
from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose
from app.models.user import User
from app.services.email_otp_challenges import EmailOtpChallengeService

REGISTER_URL = "/api/v1/auth/register"
OTP_REQUEST_URL = "/api/v1/auth/email-verification/otp/request"
OTP_CONFIRM_URL = "/api/v1/auth/email-verification/otp/confirm"
INVALID_DETAIL = "Invalid or expired email verification code."
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


def _assert_invalid(response) -> None:
    assert response.status_code == 400
    assert response.json() == {"detail": INVALID_DETAIL}


async def _register_and_request_code(
    client: AsyncClient,
    mailer: FakeEmailVerificationOtpMailer,
    *,
    email: str,
) -> tuple[dict, str]:
    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "OTP Confirm User",
            "password": PASSWORD,
        },
    )
    assert register_response.status_code == 201

    before_calls = len(mailer.calls)
    request_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": email},
    )
    assert request_response.status_code == 202
    assert len(mailer.calls) == before_calls + 1

    return register_response.json(), mailer.calls[-1][1]


@pytest.mark.asyncio
async def test_otp_confirm_supports_leading_zero_and_is_single_use(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        "app.services.email_otp_challenges.generate_email_otp_code",
        lambda: "001234",
    )
    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)
    registered_user, code = await _register_and_request_code(
        client,
        mailer,
        email="otp-leading-zero@example.com",
    )
    assert code == "001234"

    response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "  OTP-LEADING-ZERO@EXAMPLE.COM  ",
            "code": code,
        },
    )

    assert response.status_code == 204
    assert response.content == b""
    assert code not in response.text
    assert code not in caplog.text

    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(registered_user["id"]))
    assert user is not None
    assert user.email_verified_at is not None

    challenge_result = await db_session.execute(
        select(EmailOtpChallenge).where(
            EmailOtpChallenge.user_id == user.id,
            EmailOtpChallenge.purpose == EmailOtpPurpose.EMAIL_VERIFICATION,
        )
    )
    challenge = challenge_result.scalar_one()
    assert challenge.used_at is not None
    assert challenge.revoked_at is None
    await db_session.commit()

    reuse_response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-leading-zero@example.com",
            "code": code,
        },
    )
    _assert_invalid(reuse_response)


@pytest.mark.asyncio
async def test_wrong_code_commits_failed_attempt_without_verifying_user(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)
    registered_user, code = await _register_and_request_code(
        client,
        mailer,
        email="otp-wrong-api@example.com",
    )
    wrong_code = "000000" if code != "000000" else "000001"

    response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-wrong-api@example.com",
            "code": wrong_code,
        },
    )
    _assert_invalid(response)

    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(registered_user["id"]))
    assert user is not None
    assert user.email_verified_at is None

    challenge_result = await db_session.execute(
        select(EmailOtpChallenge).where(
            EmailOtpChallenge.user_id == user.id,
            EmailOtpChallenge.purpose == EmailOtpPurpose.EMAIL_VERIFICATION,
        )
    )
    challenge = challenge_result.scalar_one()
    assert challenge.failed_attempts == 1
    assert challenge.used_at is None


@pytest.mark.asyncio
async def test_otp_confirm_enforces_attempt_limit(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)
    registered_user, code = await _register_and_request_code(
        client,
        mailer,
        email="otp-attempt-limit-api@example.com",
    )
    wrong_code = "999999" if code != "999999" else "999998"

    for _ in range(5):
        response = await client.post(
            OTP_CONFIRM_URL,
            json={
                "email": "otp-attempt-limit-api@example.com",
                "code": wrong_code,
            },
        )
        _assert_invalid(response)

    correct_after_limit = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-attempt-limit-api@example.com",
            "code": code,
        },
    )
    _assert_invalid(correct_after_limit)

    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(registered_user["id"]))
    assert user is not None
    assert user.email_verified_at is None

    challenge_result = await db_session.execute(
        select(EmailOtpChallenge).where(
            EmailOtpChallenge.user_id == user.id,
            EmailOtpChallenge.purpose == EmailOtpPurpose.EMAIL_VERIFICATION,
        )
    )
    assert challenge_result.scalar_one().failed_attempts == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["expired", "revoked"])
async def test_otp_confirm_returns_same_error_for_inactive_challenge_states(
    client: AsyncClient,
    db_session: AsyncSession,
    state: str,
) -> None:
    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)
    registered_user, code = await _register_and_request_code(
        client,
        mailer,
        email=f"otp-{state}-api@example.com",
    )

    async with db_session.begin():
        challenge_result = await db_session.execute(
            select(EmailOtpChallenge).where(
                EmailOtpChallenge.user_id == uuid.UUID(registered_user["id"]),
                EmailOtpChallenge.purpose == EmailOtpPurpose.EMAIL_VERIFICATION,
            )
        )
        challenge = challenge_result.scalar_one()
        if state == "expired":
            challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        else:
            challenge.revoked_at = datetime.now(UTC)

    response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": f"otp-{state}-api@example.com",
            "code": code,
        },
    )
    _assert_invalid(response)

    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(registered_user["id"]))
    assert user is not None
    assert user.email_verified_at is None


@pytest.mark.asyncio
async def test_otp_confirm_rejects_unknown_user_and_wrong_purpose(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    unknown_response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "unknown-otp-confirm@example.com",
            "code": "123456",
        },
    )
    _assert_invalid(unknown_response)

    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)
    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": "otp-purpose-api@example.com",
            "full_name": "OTP Purpose User",
            "password": PASSWORD,
        },
    )
    assert register_response.status_code == 201
    user_id = uuid.UUID(register_response.json()["id"])

    service = EmailOtpChallengeService(db_session)
    password_reset_delivery = await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="otp-purpose-api@example.com",
    )

    purpose_response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-purpose-api@example.com",
            "code": password_reset_delivery.code.get_secret_value(),
        },
    )
    _assert_invalid(purpose_response)


@pytest.mark.asyncio
async def test_resend_revokes_previous_otp_code(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)
    registered_user, first_code = await _register_and_request_code(
        client,
        mailer,
        email="otp-resend-api@example.com",
    )
    user_id = uuid.UUID(registered_user["id"])

    async with db_session.begin():
        challenge_result = await db_session.execute(
            select(EmailOtpChallenge).where(
                EmailOtpChallenge.user_id == user_id,
                EmailOtpChallenge.purpose == EmailOtpPurpose.EMAIL_VERIFICATION,
            )
        )
        challenge_result.scalar_one().last_sent_at = datetime.now(UTC) - timedelta(
            minutes=2
        )

    resend_response = await client.post(
        OTP_REQUEST_URL,
        json={"email": "otp-resend-api@example.com"},
    )
    assert resend_response.status_code == 202
    assert len(mailer.calls) == 2
    second_code = mailer.calls[-1][1]
    assert second_code != first_code

    first_response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-resend-api@example.com",
            "code": first_code,
        },
    )
    _assert_invalid(first_response)

    second_response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-resend-api@example.com",
            "code": second_code,
        },
    )
    assert second_response.status_code == 204

    challenge_result = await db_session.execute(
        select(EmailOtpChallenge)
        .where(
            EmailOtpChallenge.user_id == user_id,
            EmailOtpChallenge.purpose == EmailOtpPurpose.EMAIL_VERIFICATION,
        )
        .order_by(
            EmailOtpChallenge.created_at.asc(),
            EmailOtpChallenge.id.asc(),
        )
    )
    challenges = list(challenge_result.scalars())
    assert len(challenges) == 2
    assert challenges[0].revoked_at is not None
    assert challenges[1].used_at is not None


@pytest.mark.asyncio
async def test_concurrent_otp_confirm_succeeds_only_once(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(mailer)
    registered_user, code = await _register_and_request_code(
        client,
        mailer,
        email="otp-concurrent-api@example.com",
    )

    first_response, second_response = await asyncio.gather(
        client.post(
            OTP_CONFIRM_URL,
            json={
                "email": "otp-concurrent-api@example.com",
                "code": code,
            },
        ),
        client.post(
            OTP_CONFIRM_URL,
            json={
                "email": "otp-concurrent-api@example.com",
                "code": code,
            },
        ),
    )

    assert sorted([first_response.status_code, second_response.status_code]) == [
        204,
        400,
    ]

    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(registered_user["id"]))
    assert user is not None
    assert user.email_verified_at is not None

    challenge_result = await db_session.execute(
        select(EmailOtpChallenge).where(
            EmailOtpChallenge.user_id == user.id,
            EmailOtpChallenge.purpose == EmailOtpPurpose.EMAIL_VERIFICATION,
        )
    )
    assert challenge_result.scalar_one().used_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "12345",
        "1234567",
        "12a456",
        "１２３４５６",
    ],
)
async def test_otp_confirm_rejects_non_six_ascii_digit_codes(
    client: AsyncClient,
    code: str,
) -> None:
    response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "format-check@example.com",
            "code": code,
        },
    )

    assert response.status_code == 422
