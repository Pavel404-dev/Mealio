import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_password_reset_mailer
from app.core.security import hash_password_reset_token, verify_password
from app.main import app
from app.models.auth_session import AuthSession
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.repositories.auth_sessions import AuthSessionsRepository
from app.repositories.users import UsersRepository

CONFIRM_RESET_URL = "/api/v1/auth/password-reset/confirm"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
REGISTER_URL = "/api/v1/auth/register"
REQUEST_RESET_URL = "/api/v1/auth/password-reset/request"
INVALID_RESET_DETAIL = "Invalid or expired password reset token."
OLD_PASSWORD = "Mealio-password-123"
NEW_PASSWORD = "Mealio-new-password-456"


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
    email: str = "reset-confirm@example.com",
    password: str = OLD_PASSWORD,
) -> dict:
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Reset Confirm User",
            "password": password,
        },
    )
    assert response.status_code == 201
    return response.json()


async def _login(
    client: AsyncClient,
    *,
    email: str = "reset-confirm@example.com",
    password: str = OLD_PASSWORD,
) -> dict:
    response = await client.post(
        LOGIN_URL,
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


async def _request_reset_token(
    client: AsyncClient,
    mailer: FakePasswordResetMailer,
    *,
    email: str = "reset-confirm@example.com",
) -> str:
    before_calls = len(mailer.calls)
    response = await client.post(
        REQUEST_RESET_URL,
        json={"email": email},
    )
    assert response.status_code == 202
    assert len(mailer.calls) == before_calls + 1
    return mailer.calls[-1][1]


def _assert_invalid_reset(response) -> None:
    assert response.status_code == 400
    assert response.json()["detail"] == INVALID_RESET_DETAIL


@pytest.mark.asyncio
async def test_confirm_reset_changes_password_consumes_token_and_revokes_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    registered_user = await _register_user(client)
    first_tokens = await _login(client)
    second_tokens = await _login(client)
    reset_token = await _request_reset_token(client, mailer)

    response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 204
    assert response.content == b""

    db_session.expire_all()
    reset_result = await db_session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_password_reset_token(reset_token)
        )
    )
    reset_record = reset_result.scalar_one()
    assert reset_record.used_at is not None
    assert reset_record.revoked_at is None

    session_result = await db_session.execute(
        select(AuthSession).where(
            AuthSession.user_id == uuid.UUID(registered_user["id"])
        )
    )
    old_sessions = session_result.scalars().all()
    assert len(old_sessions) == 2
    assert all(session.revoked_at is not None for session in old_sessions)

    for old_refresh_token in (
        first_tokens["refresh_token"],
        second_tokens["refresh_token"],
    ):
        refresh_response = await client.post(
            REFRESH_URL,
            json={"refresh_token": old_refresh_token},
        )
        assert refresh_response.status_code == 401

    old_login = await client.post(
        LOGIN_URL,
        json={
            "email": "reset-confirm@example.com",
            "password": OLD_PASSWORD,
        },
    )
    new_login = await client.post(
        LOGIN_URL,
        json={
            "email": "reset-confirm@example.com",
            "password": NEW_PASSWORD,
        },
    )

    assert old_login.status_code == 401
    assert new_login.status_code == 200

    reuse_response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": reset_token, "new_password": "Another-password-789"},
    )
    _assert_invalid_reset(reuse_response)


@pytest.mark.asyncio
async def test_confirm_reset_returns_same_error_for_unknown_expired_used_and_revoked(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    await _register_user(client)

    unknown_response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": "unknown-reset-token", "new_password": NEW_PASSWORD},
    )

    expired_token = await _request_reset_token(client, mailer)
    await db_session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == hash_password_reset_token(expired_token)
        )
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()
    expired_response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": expired_token, "new_password": NEW_PASSWORD},
    )

    used_token = await _request_reset_token(client, mailer)
    used_success = await client.post(
        CONFIRM_RESET_URL,
        json={"token": used_token, "new_password": NEW_PASSWORD},
    )
    assert used_success.status_code == 204
    used_response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": used_token, "new_password": "Another-password-789"},
    )

    revoked_token = await _request_reset_token(client, mailer)
    replacement_token = await _request_reset_token(client, mailer)
    assert replacement_token != revoked_token
    revoked_response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": revoked_token, "new_password": "Third-new-password-123"},
    )

    for response in (
        unknown_response,
        expired_response,
        used_response,
        revoked_response,
    ):
        _assert_invalid_reset(response)


@pytest.mark.asyncio
async def test_invalid_new_password_does_not_consume_reset_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    await _register_user(client)
    reset_token = await _request_reset_token(client, mailer)

    invalid_response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": reset_token, "new_password": "too-short"},
    )
    assert invalid_response.status_code == 422

    db_session.expire_all()
    result = await db_session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_password_reset_token(reset_token)
        )
    )
    reset_record = result.scalar_one()
    assert reset_record.used_at is None
    assert reset_record.revoked_at is None

    valid_response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )
    assert valid_response.status_code == 204


@pytest.mark.asyncio
async def test_deleted_user_reset_token_fails_safely(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    registered_user = await _register_user(client)
    reset_token = await _request_reset_token(client, mailer)

    await db_session.execute(
        delete(User).where(User.id == uuid.UUID(registered_user["id"]))
    )
    await db_session.commit()

    response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )

    _assert_invalid_reset(response)


@pytest.mark.asyncio
async def test_reset_transaction_rolls_back_on_session_revocation_failure(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    registered_user = await _register_user(client)
    login_tokens = await _login(client)
    reset_token = await _request_reset_token(client, mailer)

    original_revoke_all = AuthSessionsRepository.revoke_all_for_user

    async def fail_revoke_all(
        self: AuthSessionsRepository,
        *,
        user_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        raise RuntimeError("simulated session revocation failure")

    monkeypatch.setattr(
        AuthSessionsRepository,
        "revoke_all_for_user",
        fail_revoke_all,
    )

    with pytest.raises(RuntimeError, match="simulated session revocation failure"):
        await client.post(
            CONFIRM_RESET_URL,
            json={"token": reset_token, "new_password": NEW_PASSWORD},
        )

    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(registered_user["id"]))
    assert user is not None
    assert verify_password(OLD_PASSWORD, user.password_hash)
    assert not verify_password(NEW_PASSWORD, user.password_hash)

    reset_result = await db_session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_password_reset_token(reset_token)
        )
    )
    reset_record = reset_result.scalar_one()
    assert reset_record.used_at is None
    assert reset_record.revoked_at is None

    session_result = await db_session.execute(
        select(AuthSession).where(
            AuthSession.refresh_token_hash.is_not(None),
            AuthSession.user_id == uuid.UUID(registered_user["id"]),
        )
    )
    auth_session = session_result.scalar_one()
    assert auth_session.revoked_at is None

    refresh_response = await client.post(
        REFRESH_URL,
        json={"refresh_token": login_tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200

    monkeypatch.setattr(
        AuthSessionsRepository,
        "revoke_all_for_user",
        original_revoke_all,
    )
    retry_response = await client.post(
        CONFIRM_RESET_URL,
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )
    assert retry_response.status_code == 204


@pytest.mark.asyncio
async def test_concurrent_confirm_allows_exactly_one_success(
    client: AsyncClient,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    await _register_user(client)
    reset_token = await _request_reset_token(client, mailer)
    first_password = "Concurrent-password-111"
    second_password = "Concurrent-password-222"

    first_response, second_response = await asyncio.gather(
        client.post(
            CONFIRM_RESET_URL,
            json={"token": reset_token, "new_password": first_password},
        ),
        client.post(
            CONFIRM_RESET_URL,
            json={"token": reset_token, "new_password": second_password},
        ),
    )

    assert sorted([first_response.status_code, second_response.status_code]) == [
        204,
        400,
    ]

    old_login = await client.post(
        LOGIN_URL,
        json={"email": "reset-confirm@example.com", "password": OLD_PASSWORD},
    )
    first_login = await client.post(
        LOGIN_URL,
        json={"email": "reset-confirm@example.com", "password": first_password},
    )
    second_login = await client.post(
        LOGIN_URL,
        json={"email": "reset-confirm@example.com", "password": second_password},
    )

    assert old_login.status_code == 401
    assert sorted([first_login.status_code, second_login.status_code]) == [200, 401]


@pytest.mark.asyncio
async def test_refresh_racing_with_reset_cannot_leave_usable_old_session(
    client: AsyncClient,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    await _register_user(client)
    login_tokens = await _login(client)
    reset_token = await _request_reset_token(client, mailer)

    reset_response, refresh_response = await asyncio.gather(
        client.post(
            CONFIRM_RESET_URL,
            json={"token": reset_token, "new_password": NEW_PASSWORD},
        ),
        client.post(
            REFRESH_URL,
            json={"refresh_token": login_tokens["refresh_token"]},
        ),
    )

    assert reset_response.status_code == 204
    assert refresh_response.status_code in {200, 401}

    candidate_refresh_token = (
        refresh_response.json()["refresh_token"]
        if refresh_response.status_code == 200
        else login_tokens["refresh_token"]
    )
    after_reset_refresh = await client.post(
        REFRESH_URL,
        json={"refresh_token": candidate_refresh_token},
    )
    assert after_reset_refresh.status_code == 401


@pytest.mark.asyncio
async def test_login_with_old_password_racing_reset_cannot_survive_reset(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    await _register_user(client)
    reset_token = await _request_reset_token(client, mailer)

    original_get_by_email_for_update = UsersRepository.get_by_email_for_update
    login_has_user_lock = asyncio.Event()
    allow_login_to_continue = asyncio.Event()
    should_delay_login = True

    async def delayed_get_by_email_for_update(
        self: UsersRepository,
        email: str,
    ) -> User | None:
        nonlocal should_delay_login
        user = await original_get_by_email_for_update(self, email)

        if should_delay_login and email.strip().lower() == "reset-confirm@example.com":
            should_delay_login = False
            login_has_user_lock.set()
            await allow_login_to_continue.wait()

        return user

    monkeypatch.setattr(
        UsersRepository,
        "get_by_email_for_update",
        delayed_get_by_email_for_update,
    )

    login_task = asyncio.create_task(
        client.post(
            LOGIN_URL,
            json={
                "email": "reset-confirm@example.com",
                "password": OLD_PASSWORD,
            },
        )
    )
    await asyncio.wait_for(login_has_user_lock.wait(), timeout=5)

    reset_task = asyncio.create_task(
        client.post(
            CONFIRM_RESET_URL,
            json={"token": reset_token, "new_password": NEW_PASSWORD},
        )
    )
    await asyncio.sleep(0.05)
    allow_login_to_continue.set()

    login_response, reset_response = await asyncio.gather(login_task, reset_task)

    assert login_response.status_code == 200
    assert reset_response.status_code == 204

    refresh_response = await client.post(
        REFRESH_URL,
        json={"refresh_token": login_response.json()["refresh_token"]},
    )
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"token": None, "new_password": NEW_PASSWORD},
        {"token": "", "new_password": NEW_PASSWORD},
        {"token": "x" * 513, "new_password": NEW_PASSWORD},
        {"token": "some-token", "new_password": "short"},
        {"token": "some-token", "new_password": " " * 15},
        {"token": "some-token", "new_password": "x" * 129},
    ],
)
async def test_confirm_reset_rejects_invalid_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await client.post(CONFIRM_RESET_URL, json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_new_reset_request_racing_confirm_does_not_deadlock(
    client: AsyncClient,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    await _register_user(client)
    old_reset_token = await _request_reset_token(client, mailer)

    confirm_task = client.post(
        CONFIRM_RESET_URL,
        json={"token": old_reset_token, "new_password": NEW_PASSWORD},
    )
    request_task = client.post(
        REQUEST_RESET_URL,
        json={"email": "reset-confirm@example.com"},
    )

    confirm_response, request_response = await asyncio.wait_for(
        asyncio.gather(confirm_task, request_task),
        timeout=10,
    )

    assert confirm_response.status_code in {204, 400}
    assert request_response.status_code == 202
    assert len(mailer.calls) == 2

    newest_reset_token = mailer.calls[-1][1]
    assert newest_reset_token != old_reset_token

    newest_confirm = await client.post(
        CONFIRM_RESET_URL,
        json={
            "token": newest_reset_token,
            "new_password": "Newest-reset-password-789",
        },
    )
    assert newest_confirm.status_code == 204


@pytest.mark.asyncio
async def test_token_expiring_while_waiting_for_user_lock_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mailer = FakePasswordResetMailer()
    _use_fake_mailer(mailer)
    await _register_user(client)
    reset_token = await _request_reset_token(client, mailer)

    await db_session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_password_reset_token(reset_token))
        .values(expires_at=datetime.now(UTC) + timedelta(milliseconds=250))
    )
    await db_session.commit()

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
        CONFIRM_RESET_URL,
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )

    _assert_invalid_reset(response)
