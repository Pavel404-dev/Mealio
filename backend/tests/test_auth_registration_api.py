import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.user import User


REGISTER_URL = "/api/v1/auth/register"


@pytest.mark.asyncio
async def test_register_user_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    password = "Mealio-Пароль-🔐"

    response = await client.post(
        REGISTER_URL,
        json={
            "email": "  Pavel.User@Example.COM  ",
            "full_name": "  Pavel Potapenko  ",
            "password": password,
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["email"] == "pavel.user@example.com"
    assert data["full_name"] == "Pavel Potapenko"
    assert data["created_at"]
    assert data["updated_at"]
    assert "password" not in data
    assert "password_hash" not in data

    result = await db_session.execute(
        select(User).where(User.email == "pavel.user@example.com")
    )
    user = result.scalar_one_or_none()

    assert user is not None
    assert user.full_name == "Pavel Potapenko"
    assert user.password_hash is not None
    assert user.password_hash != password
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(password, user.password_hash)


@pytest.mark.asyncio
async def test_register_user_with_unicode_password(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    password = "Безопасный-Пароль-🔐"

    response = await client.post(
        REGISTER_URL,
        json={
            "email": "unicode@example.com",
            "full_name": "Unicode User",
            "password": password,
        },
    )

    assert response.status_code == 201

    result = await db_session.execute(
        select(User).where(User.email == "unicode@example.com")
    )
    user = result.scalar_one()

    assert verify_password(password, user.password_hash)


@pytest.mark.asyncio
async def test_register_preserves_password_surrounding_spaces(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    password = "  Mealio-password  "

    response = await client.post(
        REGISTER_URL,
        json={
            "email": "spaces@example.com",
            "full_name": "Spaces User",
            "password": password,
        },
    )

    assert response.status_code == 201

    result = await db_session.execute(
        select(User).where(User.email == "spaces@example.com")
    )
    user = result.scalar_one()

    assert verify_password(password, user.password_hash)
    assert not verify_password(
        password.strip(),
        user.password_hash,
    )


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(
    client: AsyncClient,
) -> None:
    first_response = await client.post(
        REGISTER_URL,
        json={
            "email": "Pavel.User@Example.COM",
            "full_name": "Pavel",
            "password": "Mealio-password-123",
        },
    )

    duplicate_response = await client.post(
        REGISTER_URL,
        json={
            "email": "  pavel.user@example.com  ",
            "full_name": "Another Pavel",
            "password": "Another-password-123",
        },
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "User with this email already exists"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "email": "not-an-email",
            "full_name": "Pavel",
            "password": "Mealio-password-123",
        },
        {
            "email": "short@example.com",
            "full_name": "Pavel",
            "password": "a" * 14,
        },
        {
            "email": "missing@example.com",
            "full_name": "Pavel",
        },
        {
            "email": "null@example.com",
            "full_name": "Pavel",
            "password": None,
        },
        {
            "email": "spaces-only@example.com",
            "full_name": "Pavel",
            "password": " " * 15,
        },
    ],
)
async def test_register_rejects_invalid_payload(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await client.post(
        REGISTER_URL,
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_allows_null_full_name(
    client: AsyncClient,
) -> None:
    response = await client.post(
        REGISTER_URL,
        json={
            "email": "nullable-name@example.com",
            "full_name": None,
            "password": "Mealio-password-123",
        },
    )

    assert response.status_code == 201
    assert response.json()["full_name"] is None


@pytest.mark.asyncio
async def test_existing_users_endpoint_still_works_without_password(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "profile@example.com",
            "full_name": "Profile User",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "profile@example.com"
