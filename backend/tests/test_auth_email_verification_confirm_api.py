import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_email_verification_mailer
from app.core.security import hash_email_verification_token
from app.main import app
from app.models.email_verification_token import EmailVerificationToken
from app.models.user import User
from app.repositories.email_verification_tokens import (
    EmailVerificationTokensRepository,
)

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
REQUEST_VERIFICATION_URL = "/api/v1/auth/email-verification/request"
CONFIRM_VERIFICATION_URL = "/api/v1/auth/email-verification/confirm"
INVALID_DETAIL = "Invalid or expired email verification token."
PASSWORD = "Mealio-password-123"


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


async def _register_with_token(
    client: AsyncClient,
    mailer: FakeEmailVerificationMailer,
    *,
    email: str,
) -> tuple[dict, str]:
    before_calls = len(mailer.calls)
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Verify Confirm User",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    assert len(mailer.calls) == before_calls + 1
    return response.json(), mailer.calls[-1][1]


async def _login(
    client: AsyncClient,
    *,
    email: str,
) -> dict:
    response = await client.post(
        LOGIN_URL,
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def _assert_invalid(response) -> None:
    assert response.status_code == 400
    assert response.json() == {"detail": INVALID_DETAIL}


@pytest.mark.asyncio
async def test_confirm_verification_marks_user_verified_and_keeps_session_valid(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    registered_user, verification_token = await _register_with_token(
        client,
        mailer,
        email="confirm-success@example.com",
    )
    login_tokens = await _login(client, email="confirm-success@example.com")

    response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": verification_token},
    )

    assert response.status_code == 204
    assert response.content == b""

    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(registered_user["id"]))
    assert user is not None
    assert user.email == "confirm-success@example.com"
    assert user.email_verified_at is not None

    token_result = await db_session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash
            == hash_email_verification_token(verification_token)
        )
    )
    token_record = token_result.scalar_one()
    assert token_record.used_at is not None
    assert token_record.revoked_at is None

    reuse_response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": verification_token},
    )
    _assert_invalid(reuse_response)

    refresh_response = await client.post(
        REFRESH_URL,
        json={"refresh_token": login_tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200


@pytest.mark.asyncio
async def test_confirm_returns_same_error_for_invalid_token_states(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)

    unknown_response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": "unknown-verification-token"},
    )

    _, expired_token = await _register_with_token(
        client,
        mailer,
        email="expired@example.com",
    )
    await db_session.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.token_hash
            == hash_email_verification_token(expired_token)
        )
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()
    expired_response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": expired_token},
    )

    _, revoked_token = await _register_with_token(
        client,
        mailer,
        email="revoked@example.com",
    )
    replacement_response = await client.post(
        REQUEST_VERIFICATION_URL,
        json={"email": "revoked@example.com"},
    )
    assert replacement_response.status_code == 202
    revoked_response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": revoked_token},
    )

    _, used_token = await _register_with_token(
        client,
        mailer,
        email="used@example.com",
    )
    used_success = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": used_token},
    )
    assert used_success.status_code == 204
    used_response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": used_token},
    )

    for response in (
        unknown_response,
        expired_response,
        revoked_response,
        used_response,
    ):
        _assert_invalid(response)


@pytest.mark.asyncio
async def test_deleted_user_verification_token_fails_safely(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    registered_user, verification_token = await _register_with_token(
        client,
        mailer,
        email="deleted@example.com",
    )

    await db_session.execute(
        delete(User).where(User.id == uuid.UUID(registered_user["id"]))
    )
    await db_session.commit()

    response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": verification_token},
    )

    _assert_invalid(response)


@pytest.mark.asyncio
async def test_concurrent_confirm_allows_exactly_one_success(
    client: AsyncClient,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    _, verification_token = await _register_with_token(
        client,
        mailer,
        email="concurrent-confirm@example.com",
    )

    first_response, second_response = await asyncio.gather(
        client.post(
            CONFIRM_VERIFICATION_URL,
            json={"token": verification_token},
        ),
        client.post(
            CONFIRM_VERIFICATION_URL,
            json={"token": verification_token},
        ),
    )

    assert sorted([first_response.status_code, second_response.status_code]) == [
        204,
        400,
    ]


@pytest.mark.asyncio
async def test_confirm_transaction_rolls_back_if_final_token_revocation_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    registered_user, verification_token = await _register_with_token(
        client,
        mailer,
        email="rollback-confirm@example.com",
    )

    original_revoke = EmailVerificationTokensRepository.revoke_unused_for_user
    call_count = 0

    async def fail_on_confirm_revoke(
        self: EmailVerificationTokensRepository,
        *,
        user_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated final verification revocation failure")
        await original_revoke(
            self,
            user_id=user_id,
            revoked_at=revoked_at,
        )

    monkeypatch.setattr(
        EmailVerificationTokensRepository,
        "revoke_unused_for_user",
        fail_on_confirm_revoke,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated final verification revocation failure",
    ):
        await client.post(
            CONFIRM_VERIFICATION_URL,
            json={"token": verification_token},
        )

    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(registered_user["id"]))
    assert user is not None
    assert user.email_verified_at is None

    token_result = await db_session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash
            == hash_email_verification_token(verification_token)
        )
    )
    token_record = token_result.scalar_one()
    assert token_record.used_at is None
    assert token_record.revoked_at is None


@pytest.mark.asyncio
async def test_resend_racing_confirm_never_leaves_inconsistent_state(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    registered_user, old_token = await _register_with_token(
        client,
        mailer,
        email="resend-race@example.com",
    )

    confirm_response, request_response = await asyncio.wait_for(
        asyncio.gather(
            client.post(
                CONFIRM_VERIFICATION_URL,
                json={"token": old_token},
            ),
            client.post(
                REQUEST_VERIFICATION_URL,
                json={"email": "resend-race@example.com"},
            ),
        ),
        timeout=10,
    )

    assert confirm_response.status_code in {204, 400}
    assert request_response.status_code == 202

    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(registered_user["id"]))
    assert user is not None

    active_result = await db_session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.revoked_at.is_(None),
            EmailVerificationToken.expires_at > datetime.now(UTC),
        )
    )
    active_tokens = active_result.scalars().all()

    if user.email_verified_at is not None:
        assert confirm_response.status_code == 204
        assert active_tokens == []
    else:
        assert confirm_response.status_code == 400
        assert len(active_tokens) == 1
        newest_raw_token = mailer.calls[-1][1]
        newest_confirm = await client.post(
            CONFIRM_VERIFICATION_URL,
            json={"token": newest_raw_token},
        )
        assert newest_confirm.status_code == 204


@pytest.mark.asyncio
async def test_token_expiring_while_waiting_for_user_lock_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    _, verification_token = await _register_with_token(
        client,
        mailer,
        email="expires-at-lock@example.com",
    )

    await db_session.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.token_hash
            == hash_email_verification_token(verification_token)
        )
        .values(expires_at=datetime.now(UTC) + timedelta(milliseconds=250))
    )
    await db_session.commit()

    from app.repositories.users import UsersRepository

    original_get_by_id_for_update = UsersRepository.get_by_id_for_update

    async def delayed_get_by_id_for_update(
        self: UsersRepository,
        user_id: uuid.UUID,
    ) -> User | None:
        user = await original_get_by_id_for_update(self, user_id)
        await asyncio.sleep(0.5)
        return user

    monkeypatch.setattr(
        UsersRepository,
        "get_by_id_for_update",
        delayed_get_by_id_for_update,
    )

    response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": verification_token},
    )

    _assert_invalid(response)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"token": None},
        {"token": ""},
        {"token": "x" * 513},
    ],
)
async def test_confirm_verification_rejects_invalid_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await client.post(CONFIRM_VERIFICATION_URL, json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_token_email_snapshot_mismatch_returns_generic_error(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    registered_user, verification_token = await _register_with_token(
        client,
        mailer,
        email="snapshot-old@example.com",
    )

    await db_session.execute(
        update(User)
        .where(User.id == uuid.UUID(registered_user["id"]))
        .values(email="snapshot-new@example.com")
    )
    await db_session.commit()

    response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": verification_token},
    )

    _assert_invalid(response)
