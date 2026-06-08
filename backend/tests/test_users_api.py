from uuid import uuid4

import pytest
from httpx import AsyncClient


async def create_test_user(
        client: AsyncClient,
        *,
        email: str = "pavel@example.com",
        full_name: str | None = "Pavel Potapenko",
) -> dict:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "full_name": full_name,
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_create_user_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "  Pavel.User@Example.COM  ",
            "full_name": "  Pavel Potapenko  ",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["email"] == "pavel.user@example.com"
    assert data["full_name"] == "Pavel Potapenko"
    assert data["created_at"]
    assert data["updated_at"]


@pytest.mark.asyncio
async def test_get_existing_user(client: AsyncClient) -> None:
    created_user = await create_test_user(client)

    response = await client.get(
        f"/api/v1/users/{created_user['id']}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == created_user["id"]
    assert data["email"] == "pavel@example.com"
    assert data["full_name"] == "Pavel Potapenko"


@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_email(
        client: AsyncClient,
) -> None:
    first_response = await client.post(
        "/api/v1/users",
        json={
            "email": "Pavel@Example.COM",
            "full_name": "Pavel",
        },
    )

    assert first_response.status_code == 201

    duplicate_response = await client.post(
        "/api/v1/users",
        json={
            "email": "pavel@example.com",
            "full_name": "Another Pavel",
        },
    )

    assert duplicate_response.status_code == 409
    assert (
            duplicate_response.json()["detail"]
            == "User with this email already exists"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_email",
    [
        "",
        "   ",
        "not-an-email",
        "pavel@",
        "@example.com",
    ],
)
async def test_create_user_rejects_invalid_email(
        client: AsyncClient,
        invalid_email: str,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": invalid_email,
            "full_name": "Pavel",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_missing_user_returns_404(
        client: AsyncClient,
) -> None:
    missing_user_id = uuid4()

    response = await client.get(
        f"/api/v1/users/{missing_user_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_user_response_does_not_expose_password_hash(
        client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "secure@example.com",
            "full_name": "Secure User",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_blank_full_name_is_normalized_to_null(
        client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "blank-name@example.com",
            "full_name": "   ",
        },
    )

    assert response.status_code == 201
    assert response.json()["full_name"] is None


@pytest.mark.asyncio
async def test_update_user_full_name_only(
        client: AsyncClient,
) -> None:
    created_user = await create_test_user(client)

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "full_name": "  Updated Pavel  ",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == created_user["id"]
    assert data["email"] == created_user["email"]
    assert data["full_name"] == "Updated Pavel"


@pytest.mark.asyncio
async def test_update_user_email_only(
        client: AsyncClient,
) -> None:
    created_user = await create_test_user(client)

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "email": "updated@example.com",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["email"] == "updated@example.com"
    assert data["full_name"] == created_user["full_name"]


@pytest.mark.asyncio
async def test_update_user_normalizes_email(
        client: AsyncClient,
) -> None:
    created_user = await create_test_user(client)

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "email": "  Updated.User@Example.COM  ",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "updated.user@example.com"


@pytest.mark.asyncio
async def test_update_user_preserves_omitted_fields(
        client: AsyncClient,
) -> None:
    created_user = await create_test_user(
        client,
        email="preserved@example.com",
        full_name="Original Name",
    )

    update_response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "full_name": "New Name",
        },
    )

    assert update_response.status_code == 200

    get_response = await client.get(
        f"/api/v1/users/{created_user['id']}"
    )

    assert get_response.status_code == 200

    data = get_response.json()

    assert data["email"] == "preserved@example.com"
    assert data["full_name"] == "New Name"


@pytest.mark.asyncio
async def test_update_user_full_name_null_clears_name(
        client: AsyncClient,
) -> None:
    created_user = await create_test_user(client)

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "full_name": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["full_name"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blank_full_name",
    [
        "",
        "   ",
    ],
)
async def test_update_user_blank_full_name_is_normalized_to_null(
        client: AsyncClient,
        blank_full_name: str,
) -> None:
    created_user = await create_test_user(client)

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "full_name": blank_full_name,
        },
    )

    assert response.status_code == 200
    assert response.json()["full_name"] is None


@pytest.mark.asyncio
async def test_update_user_rejects_duplicate_email(
        client: AsyncClient,
) -> None:
    first_user = await create_test_user(
        client,
        email="taken@example.com",
        full_name="First User",
    )
    second_user = await create_test_user(
        client,
        email="available@example.com",
        full_name="Second User",
    )

    response = await client.patch(
        f"/api/v1/users/{second_user['id']}",
        json={
            "email": "  TAKEN@EXAMPLE.COM  ",
        },
    )

    assert first_user["email"] == "taken@example.com"
    assert response.status_code == 409
    assert (
            response.json()["detail"]
            == "User with this email already exists"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_email",
    [
        "",
        "   ",
        "not-an-email",
        "pavel@",
        "@example.com",
    ],
)
async def test_update_user_rejects_invalid_email(
        client: AsyncClient,
        invalid_email: str,
) -> None:
    created_user = await create_test_user(client)

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "email": invalid_email,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_user_rejects_null_email(
        client: AsyncClient,
) -> None:
    created_user = await create_test_user(client)

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "email": None,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_missing_user_returns_404(
        client: AsyncClient,
) -> None:
    missing_user_id = uuid4()

    response = await client.patch(
        f"/api/v1/users/{missing_user_id}",
        json={
            "full_name": "Missing User",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_update_user_response_does_not_expose_password_hash(
        client: AsyncClient,
) -> None:
    created_user = await create_test_user(
        client,
        email="update-secure@example.com",
    )

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "full_name": "Updated Secure User",
        },
    )

    assert response.status_code == 200
    assert "password_hash" not in response.json()


@pytest.mark.asyncio
async def test_update_user_rejects_full_name_longer_than_255_characters(
        client: AsyncClient,
) -> None:
    created_user = await create_test_user(client)

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "full_name": "a" * 256,
        },
    )

    assert response.status_code == 422

@pytest.mark.asyncio
async def test_update_user_allows_current_email(
        client: AsyncClient,
) -> None:
    created_user = await create_test_user(
        client,
        email="Current.Email@Example.COM",
        full_name="Current User",
    )

    response = await client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={
            "email": "  CURRENT.EMAIL@EXAMPLE.COM  ",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == created_user["id"]
    assert data["email"] == "current.email@example.com"
    assert data["full_name"] == created_user["full_name"]
