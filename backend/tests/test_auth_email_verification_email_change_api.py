import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
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
ME_URL = "/api/v1/auth/me"
REQUEST_VERIFICATION_URL = "/api/v1/auth/email-verification/request"
CONFIRM_VERIFICATION_URL = "/api/v1/auth/email-verification/confirm"
PASSWORD = "Mealio-password-123"
INVALID_DETAIL = "Invalid or expired email verification token."


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


async def _register_and_login(
    client: AsyncClient,
    mailer: FakeEmailVerificationMailer,
    *,
    email: str,
) -> tuple[dict, str, dict[str, str]]:
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Email Change User",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    initial_token = mailer.calls[-1][1]

    login_response = await client.post(
        LOGIN_URL,
        json={"email": email, "password": PASSWORD},
    )
    assert login_response.status_code == 200
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
    return response.json(), initial_token, headers


@pytest.mark.asyncio
async def test_changing_verified_email_clears_verification_status(
    client: AsyncClient,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    _, initial_token, headers = await _register_and_login(
        client,
        mailer,
        email="verified-change@example.com",
    )

    confirm_response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": initial_token},
    )
    assert confirm_response.status_code == 204

    verified_me = await client.get(ME_URL, headers=headers)
    assert verified_me.status_code == 200
    assert verified_me.json()["email_verified"] is True

    update_response = await client.patch(
        ME_URL,
        headers=headers,
        json={"email": "  New.Verified.Change@Example.COM  "},
    )

    assert update_response.status_code == 200
    assert update_response.json()["email"] == "new.verified.change@example.com"
    assert update_response.json()["email_verified"] is False
    assert update_response.json()["email_verified_at"] is None


@pytest.mark.asyncio
async def test_email_change_revokes_old_token_and_new_email_can_be_verified(
    client: AsyncClient,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    _, old_token, headers = await _register_and_login(
        client,
        mailer,
        email="old-address@example.com",
    )

    update_response = await client.patch(
        ME_URL,
        headers=headers,
        json={"email": "new-address@example.com"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["email_verified"] is False

    old_confirm = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": old_token},
    )
    assert old_confirm.status_code == 400
    assert old_confirm.json() == {"detail": INVALID_DETAIL}

    request_response = await client.post(
        REQUEST_VERIFICATION_URL,
        json={"email": "new-address@example.com"},
    )
    assert request_response.status_code == 202
    assert mailer.calls[-1][0] == "new-address@example.com"
    new_token = mailer.calls[-1][1]
    assert new_token != old_token

    new_confirm = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": new_token},
    )
    assert new_confirm.status_code == 204

    me_response = await client.get(ME_URL, headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "new-address@example.com"
    assert me_response.json()["email_verified"] is True


@pytest.mark.asyncio
async def test_full_name_and_same_normalized_email_do_not_clear_verification(
    client: AsyncClient,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    registered_user, token, headers = await _register_and_login(
        client,
        mailer,
        email="keep-verified@example.com",
    )
    confirm_response = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": token},
    )
    assert confirm_response.status_code == 204

    name_response = await client.patch(
        ME_URL,
        headers=headers,
        json={"full_name": "Updated Name"},
    )
    assert name_response.status_code == 200
    assert name_response.json()["email_verified"] is True

    same_email_response = await client.patch(
        ME_URL,
        headers=headers,
        json={"email": f"  {registered_user['email'].upper()}  "},
    )
    assert same_email_response.status_code == 200
    assert same_email_response.json()["email"] == registered_user["email"]
    assert same_email_response.json()["email_verified"] is True


@pytest.mark.asyncio
async def test_email_change_racing_confirm_never_verifies_new_email_with_old_token(
    client: AsyncClient,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    _, old_token, headers = await _register_and_login(
        client,
        mailer,
        email="race-old@example.com",
    )

    update_response, confirm_response = await asyncio.wait_for(
        asyncio.gather(
            client.patch(
                ME_URL,
                headers=headers,
                json={"email": "race-new@example.com"},
            ),
            client.post(
                CONFIRM_VERIFICATION_URL,
                json={"token": old_token},
            ),
        ),
        timeout=10,
    )

    assert update_response.status_code == 200
    assert confirm_response.status_code in {204, 400}

    me_response = await client.get(ME_URL, headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "race-new@example.com"
    assert me_response.json()["email_verified"] is False
    assert me_response.json()["email_verified_at"] is None

    old_token_again = await client.post(
        CONFIRM_VERIFICATION_URL,
        json={"token": old_token},
    )
    assert old_token_again.status_code == 400
    assert old_token_again.json() == {"detail": INVALID_DETAIL}


@pytest.mark.asyncio
async def test_email_change_rolls_back_if_token_revocation_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mailer = FakeEmailVerificationMailer()
    _use_fake_mailer(mailer)
    registered_user, token, headers = await _register_and_login(
        client,
        mailer,
        email="rollback-email-change@example.com",
    )
    user_id = uuid.UUID(registered_user["id"])

    user = await db_session.get(User, user_id)
    assert user is not None
    user.email_verified_at = datetime.now(UTC)
    await db_session.commit()

    async def fail_revoke(
        self: EmailVerificationTokensRepository,
        *,
        user_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        raise RuntimeError("simulated verification-token revocation failure")

    monkeypatch.setattr(
        EmailVerificationTokensRepository,
        "revoke_unused_for_user",
        fail_revoke,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated verification-token revocation failure",
    ):
        await client.patch(
            ME_URL,
            headers=headers,
            json={"email": "rollback-new@example.com"},
        )

    db_session.expire_all()
    user = await db_session.get(User, user_id)
    assert user is not None
    assert user.email == "rollback-email-change@example.com"
    assert user.email_verified_at is not None

    token_result = await db_session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_email_verification_token(token)
        )
    )
    token_record = token_result.scalar_one()
    assert token_record.used_at is None
    assert token_record.revoked_at is None
