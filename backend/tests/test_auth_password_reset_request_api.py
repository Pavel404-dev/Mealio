import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_password_reset_mailer
from app.core.config import get_settings
from app.core.security import hash_password_reset_token
from app.main import app
from app.models.password_reset_token import PasswordResetToken

REQUEST_RESET_URL = "/api/v1/auth/password-reset/request"
REGISTER_URL = "/api/v1/auth/register"
GENERIC_MESSAGE = (
    "If an account with that email exists, password reset instructions have been sent."
)


class FakePasswordResetMailer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send_password_reset(
        self,
        *,
        recipient_email: str,
        reset_token: SecretStr,
    ) -> None:
        self.calls.append((recipient_email, reset_token.get_secret_value()))


def _use_fake_mailer(mailer: FakePasswordResetMailer) -> None:
    app.dependency_overrides[get_password_reset_mailer] = lambda: mailer


async def _register_user(
    client: AsyncClient,
    *,
    email: str = "reset-user@example.com",
) -> dict:
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Reset User",
            "password": "Mealio-password-123",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_request_reset_existing_and_unknown_email_have_same_response(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    registered_user = await _register_user(client)
    before_request = datetime.now(UTC)

    existing_response = await client.post(
        REQUEST_RESET_URL,
        json={"email": "  RESET-USER@EXAMPLE.COM  "},
    )
    unknown_response = await client.post(
        REQUEST_RESET_URL,
        json={"email": "does-not-exist@example.com"},
    )

    assert existing_response.status_code == 202
    assert unknown_response.status_code == 202
    assert (
        existing_response.json()
        == unknown_response.json()
        == {"message": GENERIC_MESSAGE}
    )
    assert len(mailer.calls) == 1

    recipient_email, raw_token = mailer.calls[0]
    assert recipient_email == "reset-user@example.com"
    assert raw_token

    result = await db_session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == uuid.UUID(registered_user["id"])
        )
    )
    reset_record = result.scalar_one()

    assert reset_record.token_hash == hash_password_reset_token(raw_token)
    assert reset_record.token_hash != raw_token
    assert len(reset_record.token_hash) == 64
    assert reset_record.used_at is None
    assert reset_record.revoked_at is None

    settings = get_settings()
    expected_expiration = before_request + timedelta(
        minutes=settings.password_reset_token_expire_minutes
    )
    assert reset_record.expires_at >= expected_expiration - timedelta(seconds=5)
    assert reset_record.expires_at <= datetime.now(UTC) + timedelta(
        minutes=settings.password_reset_token_expire_minutes,
        seconds=5,
    )

    token_count = await db_session.scalar(select(func.count(PasswordResetToken.id)))
    assert token_count == 1


@pytest.mark.asyncio
async def test_new_reset_request_revokes_previous_unused_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    await _register_user(client)

    first_response = await client.post(
        REQUEST_RESET_URL,
        json={"email": "reset-user@example.com"},
    )
    second_response = await client.post(
        REQUEST_RESET_URL,
        json={"email": "reset-user@example.com"},
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert len(mailer.calls) == 2

    first_token = mailer.calls[0][1]
    second_token = mailer.calls[1][1]
    assert first_token != second_token

    result = await db_session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash.in_(
                [
                    hash_password_reset_token(first_token),
                    hash_password_reset_token(second_token),
                ]
            )
        )
    )
    records = {record.token_hash: record for record in result.scalars().all()}

    first_record = records[hash_password_reset_token(first_token)]
    second_record = records[hash_password_reset_token(second_token)]

    assert first_record.revoked_at is not None
    assert first_record.used_at is None
    assert second_record.revoked_at is None
    assert second_record.used_at is None


@pytest.mark.asyncio
async def test_concurrent_reset_requests_leave_only_one_active_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    registered_user = await _register_user(client)

    first_response, second_response = await asyncio.gather(
        client.post(
            REQUEST_RESET_URL,
            json={"email": "reset-user@example.com"},
        ),
        client.post(
            REQUEST_RESET_URL,
            json={"email": "reset-user@example.com"},
        ),
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert len(mailer.calls) == 2

    active_result = await db_session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == uuid.UUID(registered_user["id"]),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
        )
    )
    active_records = active_result.scalars().all()

    assert len(active_records) == 1
    delivered_hashes = {
        hash_password_reset_token(raw_token) for _, raw_token in mailer.calls
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
async def test_request_reset_rejects_invalid_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)

    response = await client.post(REQUEST_RESET_URL, json=payload)

    assert response.status_code == 422
    assert mailer.calls == []


@pytest.mark.asyncio
async def test_request_reset_returns_same_503_when_delivery_is_not_configured(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register_user(client)

    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_from_email", None)
    monkeypatch.setattr(settings, "password_reset_url_base", None)

    existing_response = await client.post(
        REQUEST_RESET_URL,
        json={"email": "reset-user@example.com"},
    )
    unknown_response = await client.post(
        REQUEST_RESET_URL,
        json={"email": "does-not-exist@example.com"},
    )

    expected_body = {"detail": "Password reset delivery is not configured"}

    assert existing_response.status_code == 503
    assert unknown_response.status_code == 503
    assert existing_response.json() == unknown_response.json() == expected_body

    token_count = await db_session.scalar(select(func.count(PasswordResetToken.id)))
    assert token_count == 0
