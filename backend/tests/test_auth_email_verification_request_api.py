import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_email_verification_mailer
from app.core.config import get_settings
from app.core.security import hash_email_verification_token
from app.main import app
from app.models.email_verification_token import EmailVerificationToken
from app.models.user import User
from app.repositories.email_verification_tokens import (
    EmailVerificationTokensRepository,
)

REGISTER_URL = "/api/v1/auth/register"
REQUEST_VERIFICATION_URL = "/api/v1/auth/email-verification/request"
CONFIRM_VERIFICATION_URL = "/api/v1/auth/email-verification/confirm"
GENERIC_MESSAGE = (
    "If verification is needed for that email, "
    "verification instructions have been sent."
)


class FakeEmailVerificationMailer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send_email_verification(
        self,
        *,
        recipient_email: str,
        verification_token: SecretStr,
    ) -> None:
        self.calls.append((recipient_email, verification_token.get_secret_value()))


def _use_fake_mailer(mailer: FakeEmailVerificationMailer) -> None:
    app.dependency_overrides[get_email_verification_mailer] = lambda: mailer


async def _register_user(
    client: AsyncClient,
    *,
    email: str = "verify-user@example.com",
) -> dict:
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Verify User",
            "password": "Mealio-password-123",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_registration_creates_unverified_user_and_hashed_token(
    client: AsyncClient,
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    before_request = datetime.now(UTC)

    response = await client.post(
        REGISTER_URL,
        json={
            "email": "  New.Verify@Example.COM  ",
            "full_name": "New Verify",
            "password": "Mealio-password-123",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new.verify@example.com"
    assert data["email_verified"] is False
    assert data["email_verified_at"] is None
    assert len(mailer.calls) == 1

    recipient_email, raw_token = mailer.calls[0]
    assert recipient_email == "new.verify@example.com"
    assert raw_token
    assert raw_token not in response.text
    assert raw_token not in caplog.text

    result = await db_session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == uuid.UUID(data["id"])
        )
    )
    token_record = result.scalar_one()

    assert token_record.email == "new.verify@example.com"
    assert token_record.token_hash == hash_email_verification_token(raw_token)
    assert token_record.token_hash != raw_token
    assert len(token_record.token_hash) == 64
    assert token_record.used_at is None
    assert token_record.revoked_at is None

    settings = get_settings()
    expected_expiration = before_request + timedelta(
        hours=settings.email_verification_token_expire_hours
    )
    assert token_record.expires_at >= expected_expiration - timedelta(seconds=5)
    assert token_record.expires_at <= datetime.now(UTC) + timedelta(
        hours=settings.email_verification_token_expire_hours,
        seconds=5,
    )


@pytest.mark.asyncio
async def test_registration_rolls_back_user_when_verification_token_creation_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)

    def fail_add(self, **kwargs) -> None:
        raise RuntimeError("simulated verification-token persistence failure")

    monkeypatch.setattr(EmailVerificationTokensRepository, "add", fail_add)

    with pytest.raises(
        RuntimeError,
        match="simulated verification-token persistence failure",
    ):
        await client.post(
            REGISTER_URL,
            json={
                "email": "rollback-registration@example.com",
                "full_name": "Rollback Registration",
                "password": "Mealio-password-123",
            },
        )

    user_count = await db_session.scalar(
        select(func.count(User.id)).where(
            User.email == "rollback-registration@example.com"
        )
    )
    token_count = await db_session.scalar(select(func.count(EmailVerificationToken.id)))

    assert user_count == 0
    assert token_count == 0
    assert mailer.calls == []


@pytest.mark.asyncio
async def test_registration_returns_503_before_creating_user_when_delivery_unconfigured(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.dependency_overrides.pop(get_email_verification_mailer, None)
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_from_email", None)
    monkeypatch.setattr(settings, "email_verification_url_base", None)

    response = await client.post(
        REGISTER_URL,
        json={
            "email": "delivery-unconfigured@example.com",
            "full_name": "No Delivery",
            "password": "Mealio-password-123",
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Email verification delivery is not configured"
    }
    user_count = await db_session.scalar(select(func.count(User.id)))
    token_count = await db_session.scalar(select(func.count(EmailVerificationToken.id)))
    assert user_count == 0
    assert token_count == 0


@pytest.mark.asyncio
async def test_request_verification_has_same_response_for_all_account_states(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    await _register_user(client)
    assert len(mailer.calls) == 1

    unverified_response = await client.post(
        REQUEST_VERIFICATION_URL,
        json={"email": "  VERIFY-USER@EXAMPLE.COM  "},
    )
    assert len(mailer.calls) == 2
    newest_token = mailer.calls[-1][1]

    confirm_response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": newest_token},
    )
    assert confirm_response.status_code == 204

    verified_response = await client.post(
        REQUEST_VERIFICATION_URL,
        json={"email": "verify-user@example.com"},
    )
    unknown_response = await client.post(
        REQUEST_VERIFICATION_URL,
        json={"email": "unknown@example.com"},
    )

    assert (
        unverified_response.status_code
        == verified_response.status_code
        == unknown_response.status_code
        == 202
    )
    assert (
        unverified_response.json()
        == verified_response.json()
        == unknown_response.json()
        == {"message": GENERIC_MESSAGE}
    )
    assert len(mailer.calls) == 2

    token_count = await db_session.scalar(select(func.count(EmailVerificationToken.id)))
    assert token_count == 2


@pytest.mark.asyncio
async def test_new_verification_request_revokes_previous_active_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    registered_user = await _register_user(client)
    first_token = mailer.calls[-1][1]

    response = await client.post(
        REQUEST_VERIFICATION_URL,
        json={"email": "verify-user@example.com"},
    )

    assert response.status_code == 202
    assert len(mailer.calls) == 2
    second_token = mailer.calls[-1][1]
    assert second_token != first_token

    result = await db_session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == uuid.UUID(registered_user["id"])
        )
    )
    records = {record.token_hash: record for record in result.scalars().all()}
    first_record = records[hash_email_verification_token(first_token)]
    second_record = records[hash_email_verification_token(second_token)]

    assert first_record.revoked_at is not None
    assert first_record.used_at is None
    assert second_record.revoked_at is None
    assert second_record.used_at is None


@pytest.mark.asyncio
async def test_concurrent_verification_requests_leave_exactly_one_active_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    registered_user = await _register_user(client)

    first_response, second_response = await asyncio.gather(
        client.post(
            REQUEST_VERIFICATION_URL,
            json={"email": "verify-user@example.com"},
        ),
        client.post(
            REQUEST_VERIFICATION_URL,
            json={"email": "verify-user@example.com"},
        ),
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert len(mailer.calls) == 3

    result = await db_session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == uuid.UUID(registered_user["id"]),
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.revoked_at.is_(None),
        )
    )
    active_records = result.scalars().all()

    assert len(active_records) == 1
    delivered_hashes = {
        hash_email_verification_token(raw_token) for _, raw_token in mailer.calls
    }
    assert active_records[0].token_hash in delivered_hashes


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
async def test_request_verification_rejects_invalid_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)

    response = await client.post(REQUEST_VERIFICATION_URL, json=payload)

    assert response.status_code == 422
    assert mailer.calls == []


@pytest.mark.asyncio
async def test_request_verification_returns_same_503_when_delivery_unconfigured(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    await _register_user(client, email="unverified@example.com")
    await _register_user(client, email="verified@example.com")
    verified_token = mailer.calls[-1][1]
    confirm_response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": verified_token},
    )
    assert confirm_response.status_code == 204

    token_count_before = await db_session.scalar(
        select(func.count(EmailVerificationToken.id))
    )

    app.dependency_overrides.pop(get_email_verification_mailer, None)
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_from_email", None)
    monkeypatch.setattr(settings, "email_verification_url_base", None)

    responses = [
        await client.post(
            REQUEST_VERIFICATION_URL,
            json={"email": email},
        )
        for email in (
            "unverified@example.com",
            "verified@example.com",
            "unknown@example.com",
        )
    ]

    expected_body = {"detail": "Email verification delivery is not configured"}
    assert all(response.status_code == 503 for response in responses)
    assert all(response.json() == expected_body for response in responses)

    token_count_after = await db_session.scalar(
        select(func.count(EmailVerificationToken.id))
    )
    assert token_count_after == token_count_before
