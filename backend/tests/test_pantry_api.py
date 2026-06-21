from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
PANTRY_URL = "/api/v1/pantry"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str = "test-user@example.com",
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Test User",
            "password": password,
        },
    )

    assert register_response.status_code == 201

    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": email,
            "password": password,
        },
    )

    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]

    return register_response.json(), {
        "Authorization": f"Bearer {access_token}",
    }


async def create_test_ingredient(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": "Oats",
            "category": "grain",
            "nutrition_value": {
                "calories": "389",
                "protein_g": "16.9",
                "carbs_g": "66.3",
                "fat_g": "6.9",
                "portion_g": "100",
            },
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_add_list_update_and_delete_current_user_pantry_item(
    client: AsyncClient,
) -> None:
    user, headers = await create_authenticated_user(client)
    ingredient = await create_test_ingredient(client)

    add_response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "250",
        },
    )

    assert add_response.status_code == 201

    pantry_item = add_response.json()

    assert pantry_item["id"]
    assert pantry_item["user_id"] == user["id"]
    assert pantry_item["ingredient_id"] == ingredient["id"]
    assert Decimal(str(pantry_item["quantity_g"])) == Decimal("250")
    assert pantry_item["ingredient"]["name"] == "Oats"

    list_response = await client.get(
        PANTRY_URL,
        headers=headers,
    )

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    update_response = await client.patch(
        f"{PANTRY_URL}/{pantry_item['id']}",
        headers=headers,
        json={
            "quantity_g": "500",
        },
    )

    assert update_response.status_code == 200
    assert Decimal(str(update_response.json()["quantity_g"])) == Decimal("500")

    delete_response = await client.delete(
        f"{PANTRY_URL}/{pantry_item['id']}",
        headers=headers,
    )

    assert delete_response.status_code == 204

    empty_list_response = await client.get(
        PANTRY_URL,
        headers=headers,
    )

    assert empty_list_response.status_code == 200
    assert empty_list_response.json() == []


@pytest.mark.asyncio
async def test_pantry_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(PANTRY_URL)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pantry_rejects_invalid_token(
    client: AsyncClient,
) -> None:
    response = await client.get(
        PANTRY_URL,
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_pantry(
    client: AsyncClient,
) -> None:
    first_user, first_headers = await create_authenticated_user(
        client,
        email="first-user@example.com",
    )
    second_user, second_headers = await create_authenticated_user(
        client,
        email="second-user@example.com",
    )
    ingredient = await create_test_ingredient(client)

    add_response = await client.post(
        PANTRY_URL,
        headers=first_headers,
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "250",
        },
    )

    assert add_response.status_code == 201

    pantry_item = add_response.json()

    assert pantry_item["user_id"] == first_user["id"]
    assert pantry_item["user_id"] != second_user["id"]

    second_user_list_response = await client.get(
        PANTRY_URL,
        headers=second_headers,
    )

    assert second_user_list_response.status_code == 200
    assert second_user_list_response.json() == []

    second_user_update_response = await client.patch(
        f"{PANTRY_URL}/{pantry_item['id']}",
        headers=second_headers,
        json={
            "quantity_g": "500",
        },
    )

    assert second_user_update_response.status_code == 404
    assert second_user_update_response.json()["detail"] == "Pantry item not found"

    second_user_delete_response = await client.delete(
        f"{PANTRY_URL}/{pantry_item['id']}",
        headers=second_headers,
    )

    assert second_user_delete_response.status_code == 404
    assert second_user_delete_response.json()["detail"] == "Pantry item not found"


@pytest.mark.asyncio
async def test_add_duplicate_pantry_item_returns_409(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_test_ingredient(client)

    first_response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "100",
        },
    )

    assert first_response.status_code == 201

    duplicate_response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "200",
        },
    )

    assert duplicate_response.status_code == 409
    assert (
        duplicate_response.json()["detail"]
        == "Ingredient already exists in user pantry"
    )


@pytest.mark.asyncio
async def test_add_pantry_item_returns_404_when_ingredient_does_not_exist(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    missing_ingredient_id = uuid4()

    response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": str(missing_ingredient_id),
            "quantity_g": "100",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingredient not found"


@pytest.mark.asyncio
async def test_add_pantry_item_rejects_invalid_quantity(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_test_ingredient(client)

    response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "0",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_old_user_scoped_pantry_route_is_not_available(
    client: AsyncClient,
) -> None:
    user_id = uuid4()

    response = await client.get(f"/api/v1/users/{user_id}/pantry")

    assert response.status_code == 404
