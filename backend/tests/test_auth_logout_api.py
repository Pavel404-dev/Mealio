import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_refresh_token
from app.models.auth_session import AuthSession


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"


async def _register_and_login(
    client: AsyncClient,
    *,
    email: str = "logout-user@example.com",
) -> tuple[dict, dict]:
    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Logout User",
            "password": "Mealio-password-123",
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": email,
            "password": "Mealio-password-123",
        },
    )
    assert login_response.status_code == 200

    return register_response.json(), login_response.json()


@pytest.mark.asyncio
async def test_logout_revokes_refresh_session(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, tokens = await _register_and_login(client)
    refresh_token = tokens["refresh_token"]

    response = await client.post(
        LOGOUT_URL,
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 204
    assert response.content == b""

    result = await db_session.execute(
        select(AuthSession).where(
            AuthSession.refresh_token_hash == hash_refresh_token(refresh_token)
        )
    )
    auth_session = result.scalar_one()

    assert auth_session.revoked_at is not None

    refresh_response = await client.post(
        REFRESH_URL,
        json={"refresh_token": refresh_token},
    )

    assert refresh_response.status_code == 401
    assert refresh_response.json()["detail"] == "Invalid refresh token"

    me_response = await client.get(
        ME_URL,
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert me_response.status_code == 200


@pytest.mark.asyncio
async def test_logout_is_idempotent(
    client: AsyncClient,
) -> None:
    _, tokens = await _register_and_login(client)
    payload = {"refresh_token": tokens["refresh_token"]}

    first_response = await client.post(LOGOUT_URL, json=payload)
    second_response = await client.post(LOGOUT_URL, json=payload)

    assert first_response.status_code == 204
    assert second_response.status_code == 204
    assert first_response.content == b""
    assert second_response.content == b""


@pytest.mark.asyncio
async def test_logout_unknown_refresh_token_returns_204(
    client: AsyncClient,
) -> None:
    response = await client.post(
        LOGOUT_URL,
        json={"refresh_token": "unknown-refresh-token"},
    )

    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.asyncio
async def test_logout_expired_refresh_token_returns_204(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, tokens = await _register_and_login(client)
    token_hash = hash_refresh_token(tokens["refresh_token"])

    await db_session.execute(
        update(AuthSession)
        .where(AuthSession.refresh_token_hash == token_hash)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()

    response = await client.post(
        LOGOUT_URL,
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.asyncio
async def test_logout_rotated_refresh_token_returns_204(
    client: AsyncClient,
) -> None:
    _, tokens = await _register_and_login(client)
    old_refresh_token = tokens["refresh_token"]

    refresh_response = await client.post(
        REFRESH_URL,
        json={"refresh_token": old_refresh_token},
    )
    assert refresh_response.status_code == 200

    logout_response = await client.post(
        LOGOUT_URL,
        json={"refresh_token": old_refresh_token},
    )

    assert logout_response.status_code == 204
    assert logout_response.content == b""


@pytest.mark.asyncio
async def test_logout_one_session_does_not_revoke_another(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    registered_user, first_tokens = await _register_and_login(client)

    second_login_response = await client.post(
        LOGIN_URL,
        json={
            "email": "logout-user@example.com",
            "password": "Mealio-password-123",
        },
    )
    assert second_login_response.status_code == 200
    second_tokens = second_login_response.json()

    assert first_tokens["refresh_token"] != second_tokens["refresh_token"]

    logout_response = await client.post(
        LOGOUT_URL,
        json={"refresh_token": first_tokens["refresh_token"]},
    )
    assert logout_response.status_code == 204

    first_refresh_response = await client.post(
        REFRESH_URL,
        json={"refresh_token": first_tokens["refresh_token"]},
    )
    second_refresh_response = await client.post(
        REFRESH_URL,
        json={"refresh_token": second_tokens["refresh_token"]},
    )

    assert first_refresh_response.status_code == 401
    assert second_refresh_response.status_code == 200

    session_count = await db_session.scalar(
        select(func.count(AuthSession.id)).where(
            AuthSession.user_id == uuid.UUID(registered_user["id"])
        )
    )
    assert session_count == 2


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
async def test_logout_rejects_invalid_request_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await client.post(
        LOGOUT_URL,
        json=payload,
    )

    assert response.status_code == 422
