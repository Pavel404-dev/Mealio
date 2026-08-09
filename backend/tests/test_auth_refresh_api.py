import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_refresh_token
from app.models.auth_session import AuthSession
from app.models.user import User


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"


async def _register_user(
    client: AsyncClient,
    *,
    email: str = "refresh-user@example.com",
    password: str = "Mealio-password-123",
) -> dict:
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Refresh User",
            "password": password,
        },
    )

    assert response.status_code == 201
    return response.json()


async def _login_user(
    client: AsyncClient,
    *,
    email: str = "refresh-user@example.com",
    password: str = "Mealio-password-123",
) -> dict:
    response = await client.post(
        LOGIN_URL,
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_login_returns_refresh_token_and_creates_hashed_session(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    registered_user = await _register_user(client)
    before_login = datetime.now(UTC)

    tokens = await _login_user(client)

    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"
    assert tokens["refresh_token"] != tokens["access_token"]

    result = await db_session.execute(
        select(AuthSession).where(
            AuthSession.user_id == uuid.UUID(registered_user["id"])
        )
    )
    auth_session = result.scalar_one()

    raw_refresh_token = tokens["refresh_token"]
    expected_hash = hash_refresh_token(raw_refresh_token)

    assert auth_session.refresh_token_hash == expected_hash
    assert auth_session.refresh_token_hash != raw_refresh_token
    assert len(auth_session.refresh_token_hash) == 64
    assert auth_session.revoked_at is None

    settings = get_settings()
    expected_expiration = before_login + timedelta(
        days=settings.refresh_token_expire_days
    )

    assert auth_session.expires_at >= expected_expiration - timedelta(seconds=5)
    assert auth_session.expires_at <= datetime.now(UTC) + timedelta(
        days=settings.refresh_token_expire_days,
        seconds=5,
    )


@pytest.mark.asyncio
async def test_wrong_credentials_do_not_create_auth_session(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _register_user(client)

    response = await client.post(
        LOGIN_URL,
        json={
            "email": "refresh-user@example.com",
            "password": "Wrong-password-456",
        },
    )

    assert response.status_code == 401

    session_count = await db_session.scalar(select(func.count(AuthSession.id)))
    assert session_count == 0


@pytest.mark.asyncio
async def test_valid_refresh_rotates_token_without_creating_new_session(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _register_user(client)
    login_tokens = await _login_user(client)
    original_refresh_token = login_tokens["refresh_token"]

    original_result = await db_session.execute(select(AuthSession))
    original_session = original_result.scalar_one()
    original_session_id = original_session.id
    original_expires_at = original_session.expires_at

    response = await client.post(
        REFRESH_URL,
        json={"refresh_token": original_refresh_token},
    )

    assert response.status_code == 200

    rotated_tokens = response.json()
    rotated_refresh_token = rotated_tokens["refresh_token"]

    assert rotated_tokens["access_token"]
    assert rotated_refresh_token
    assert rotated_refresh_token != original_refresh_token
    assert rotated_tokens["token_type"] == "bearer"

    db_session.expire_all()
    result = await db_session.execute(select(AuthSession))
    rotated_session = result.scalar_one()

    assert rotated_session.id == original_session_id
    assert rotated_session.expires_at == original_expires_at
    assert rotated_session.refresh_token_hash == hash_refresh_token(
        rotated_refresh_token
    )
    assert rotated_session.refresh_token_hash != hash_refresh_token(
        original_refresh_token
    )

    session_count = await db_session.scalar(select(func.count(AuthSession.id)))
    assert session_count == 1


@pytest.mark.asyncio
async def test_old_refresh_token_cannot_be_reused_after_rotation(
    client: AsyncClient,
) -> None:
    await _register_user(client)
    login_tokens = await _login_user(client)
    original_refresh_token = login_tokens["refresh_token"]

    first_refresh = await client.post(
        REFRESH_URL,
        json={"refresh_token": original_refresh_token},
    )

    assert first_refresh.status_code == 200

    reuse_response = await client.post(
        REFRESH_URL,
        json={"refresh_token": original_refresh_token},
    )

    assert reuse_response.status_code == 401
    assert reuse_response.json()["detail"] == "Invalid refresh token"


@pytest.mark.asyncio
async def test_rotated_refresh_token_can_be_used(
    client: AsyncClient,
) -> None:
    await _register_user(client)
    login_tokens = await _login_user(client)

    first_refresh = await client.post(
        REFRESH_URL,
        json={"refresh_token": login_tokens["refresh_token"]},
    )

    assert first_refresh.status_code == 200

    second_refresh = await client.post(
        REFRESH_URL,
        json={"refresh_token": first_refresh.json()["refresh_token"]},
    )

    assert second_refresh.status_code == 200
    assert (
        second_refresh.json()["refresh_token"] != first_refresh.json()["refresh_token"]
    )


@pytest.mark.asyncio
async def test_refresh_access_token_subject_comes_from_session_owner(
    client: AsyncClient,
) -> None:
    registered_user = await _register_user(client)
    login_tokens = await _login_user(client)

    response = await client.post(
        REFRESH_URL,
        json={"refresh_token": login_tokens["refresh_token"]},
    )

    assert response.status_code == 200

    settings = get_settings()
    decoded_access_token = jwt.decode(
        response.json()["access_token"],
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert decoded_access_token["sub"] == registered_user["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "refresh_token",
    [
        "unknown-refresh-token",
        "not.a.jwt",
        "   ",
    ],
)
async def test_unknown_or_malformed_refresh_token_returns_generic_401(
    client: AsyncClient,
    refresh_token: str,
) -> None:
    response = await client.post(
        REFRESH_URL,
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"refresh_token": None},
        {"refresh_token": ""},
        {"refresh_token": "x" * 513},
    ],
)
async def test_refresh_rejects_invalid_request_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await client.post(
        REFRESH_URL,
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_expired_refresh_token_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _register_user(client)
    login_tokens = await _login_user(client)
    token_hash = hash_refresh_token(login_tokens["refresh_token"])

    await db_session.execute(
        update(AuthSession)
        .where(AuthSession.refresh_token_hash == token_hash)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()

    response = await client.post(
        REFRESH_URL,
        json={"refresh_token": login_tokens["refresh_token"]},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token"


@pytest.mark.asyncio
async def test_revoked_refresh_token_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _register_user(client)
    login_tokens = await _login_user(client)
    token_hash = hash_refresh_token(login_tokens["refresh_token"])

    await db_session.execute(
        update(AuthSession)
        .where(AuthSession.refresh_token_hash == token_hash)
        .values(revoked_at=datetime.now(UTC))
    )
    await db_session.commit()

    response = await client.post(
        REFRESH_URL,
        json={"refresh_token": login_tokens["refresh_token"]},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token"


@pytest.mark.asyncio
async def test_refresh_for_deleted_user_fails_safely(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    registered_user = await _register_user(client)
    login_tokens = await _login_user(client)

    await db_session.execute(
        delete(User).where(User.id == uuid.UUID(registered_user["id"]))
    )
    await db_session.commit()

    response = await client.post(
        REFRESH_URL,
        json={"refresh_token": login_tokens["refresh_token"]},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token"


@pytest.mark.asyncio
async def test_two_logins_create_independent_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    registered_user = await _register_user(client)

    first_login = await _login_user(client)
    second_login = await _login_user(client)

    assert first_login["refresh_token"] != second_login["refresh_token"]

    session_count = await db_session.scalar(
        select(func.count(AuthSession.id)).where(
            AuthSession.user_id == uuid.UUID(registered_user["id"])
        )
    )
    assert session_count == 2


@pytest.mark.asyncio
async def test_concurrent_refresh_allows_only_one_rotation(
    client: AsyncClient,
) -> None:
    await _register_user(client)
    login_tokens = await _login_user(client)
    refresh_token = login_tokens["refresh_token"]

    first_response, second_response = await asyncio.gather(
        client.post(
            REFRESH_URL,
            json={"refresh_token": refresh_token},
        ),
        client.post(
            REFRESH_URL,
            json={"refresh_token": refresh_token},
        ),
    )

    responses = [first_response, second_response]
    statuses = sorted(response.status_code for response in responses)

    assert statuses == [200, 401]

    successful_response = next(
        response for response in responses if response.status_code == 200
    )
    failed_response = next(
        response for response in responses if response.status_code == 401
    )

    assert failed_response.json()["detail"] == "Invalid refresh token"

    next_refresh = await client.post(
        REFRESH_URL,
        json={
            "refresh_token": successful_response.json()["refresh_token"],
        },
    )

    assert next_refresh.status_code == 200
