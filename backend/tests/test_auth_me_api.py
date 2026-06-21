from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


@pytest.mark.asyncio
async def test_auth_me_returns_current_user(
    client: AsyncClient,
) -> None:
    password = "Mealio-password-123"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": "  Pavel.User@Example.COM  ",
            "full_name": "Pavel Potapenko",
            "password": password,
        },
    )

    assert register_response.status_code == 201

    registered_user = register_response.json()

    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": "  pavel.user@example.com  ",
            "password": password,
        },
    )

    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]

    me_response = await client.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert me_response.status_code == 200

    current_user = me_response.json()

    assert current_user["id"] == registered_user["id"]
    assert current_user["email"] == "pavel.user@example.com"
    assert current_user["full_name"] == "Pavel Potapenko"
    assert current_user["created_at"]
    assert current_user["updated_at"]

    assert "password" not in current_user
    assert "password_hash" not in current_user


@pytest.mark.asyncio
async def test_auth_me_without_token_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get(ME_URL)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_with_invalid_token_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get(
        ME_URL,
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_auth_me_with_token_without_subject_returns_401(
    client: AsyncClient,
) -> None:
    settings = get_settings()

    token = jwt.encode(
        {
            "exp": datetime.now(UTC) + timedelta(minutes=30),
            "iat": datetime.now(UTC),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = await client.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_auth_me_with_invalid_user_id_returns_401(
    client: AsyncClient,
) -> None:
    settings = get_settings()

    token = jwt.encode(
        {
            "sub": "not-a-valid-uuid",
            "exp": datetime.now(UTC) + timedelta(minutes=30),
            "iat": datetime.now(UTC),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = await client.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_auth_me_with_unknown_user_returns_401(
    client: AsyncClient,
) -> None:
    settings = get_settings()

    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "exp": datetime.now(UTC) + timedelta(minutes=30),
            "iat": datetime.now(UTC),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = await client.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_auth_me_with_expired_token_returns_401(
    client: AsyncClient,
) -> None:
    settings = get_settings()

    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "exp": datetime.now(UTC) - timedelta(minutes=1),
            "iat": datetime.now(UTC) - timedelta(minutes=30),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = await client.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
