import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"


@pytest.mark.asyncio
async def test_login_user_success(
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

    user_id = register_response.json()["id"]

    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": "  pavel.user@example.com  ",
            "password": password,
        },
    )

    assert login_response.status_code == 200

    data = login_response.json()

    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert "password" not in data
    assert "password_hash" not in data

    settings = get_settings()

    decoded_token = jwt.decode(
        data["access_token"],
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert decoded_token["sub"] == user_id
    assert decoded_token["exp"]
    assert decoded_token["iat"]


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(
    client: AsyncClient,
) -> None:
    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": "wrong-password@example.com",
            "full_name": "Wrong Password User",
            "password": "Mealio-password-123",
        },
    )

    assert register_response.status_code == 201

    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": "wrong-password@example.com",
            "password": "Wrong-password-456",
        },
    )

    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_with_unknown_email_returns_401(
    client: AsyncClient,
) -> None:
    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": "unknown@example.com",
            "password": "Mealio-password-123",
        },
    )

    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_user_without_password_hash_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        email="profile-only@example.com",
        full_name="Profile Only User",
        password_hash=None,
    )

    db_session.add(user)
    await db_session.commit()

    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": "profile-only@example.com",
            "password": "Mealio-password-123",
        },
    )

    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "email": "not-an-email",
            "password": "Mealio-password-123",
        },
        {
            "email": "missing-password@example.com",
        },
        {
            "email": "null-password@example.com",
            "password": None,
        },
        {
            "email": "empty-password@example.com",
            "password": "",
        },
    ],
)
async def test_login_rejects_invalid_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await client.post(
        LOGIN_URL,
        json=payload,
    )

    assert response.status_code == 422
