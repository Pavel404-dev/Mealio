from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
PANTRY_URL = "/api/v1/pantry"
PANTRY_SUMMARY_URL = f"{PANTRY_URL}/summary"


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


async def create_test_ingredient(
    client: AsyncClient,
    *,
    name: str = "Oats",
    category: str = "grain",
    nutrition_value: dict[str, str] | None = None,
    include_nutrition: bool = True,
) -> dict:
    payload = {
        "name": name,
        "category": category,
    }

    if include_nutrition:
        payload["nutrition_value"] = nutrition_value or {
            "calories": "389",
            "protein_g": "16.9",
            "carbs_g": "66.3",
            "fat_g": "6.9",
            "portion_g": "100",
        }

    response = await client.post("/api/v1/ingredients", json=payload)

    assert response.status_code == 201

    return response.json()


async def add_pantry_item(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    ingredient_id: str,
    quantity_g: str,
) -> dict:
    response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": ingredient_id,
            "quantity_g": quantity_g,
        },
    )

    assert response.status_code == 201

    return response.json()


def assert_summary_totals(
    summary: dict,
    *,
    items_count: int,
    total_calories: str,
    total_protein_g: str,
    total_carbs_g: str,
    total_fat_g: str,
) -> None:
    assert summary["items_count"] == items_count
    assert Decimal(str(summary["total_calories"])) == Decimal(total_calories)
    assert Decimal(str(summary["total_protein_g"])) == Decimal(total_protein_g)
    assert Decimal(str(summary["total_carbs_g"])) == Decimal(total_carbs_g)
    assert Decimal(str(summary["total_fat_g"])) == Decimal(total_fat_g)


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
async def test_pantry_summary_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(PANTRY_SUMMARY_URL)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pantry_summary_rejects_invalid_token(
    client: AsyncClient,
) -> None:
    response = await client.get(
        PANTRY_SUMMARY_URL,
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_empty_pantry_summary_returns_zero_totals(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(PANTRY_SUMMARY_URL, headers=headers)

    assert response.status_code == 200
    assert_summary_totals(
        response.json(),
        items_count=0,
        total_calories="0",
        total_protein_g="0",
        total_carbs_g="0",
        total_fat_g="0",
    )


@pytest.mark.asyncio
async def test_pantry_summary_calculates_totals_from_one_ingredient(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_test_ingredient(client)

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=ingredient["id"],
        quantity_g="250",
    )

    response = await client.get(PANTRY_SUMMARY_URL, headers=headers)

    assert response.status_code == 200
    assert_summary_totals(
        response.json(),
        items_count=1,
        total_calories="972.5",
        total_protein_g="42.25",
        total_carbs_g="165.75",
        total_fat_g="17.25",
    )


@pytest.mark.asyncio
async def test_pantry_summary_calculates_totals_from_multiple_ingredients(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    chicken = await create_test_ingredient(
        client,
        name="Chicken Pantry Summary",
        nutrition_value={
            "calories": "165",
            "protein_g": "31",
            "carbs_g": "0",
            "fat_g": "3.6",
            "portion_g": "100",
        },
    )
    rice = await create_test_ingredient(
        client,
        name="Rice Pantry Summary",
        nutrition_value={
            "calories": "130",
            "protein_g": "2.7",
            "carbs_g": "28",
            "fat_g": "0.3",
            "portion_g": "100",
        },
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="200",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=rice["id"],
        quantity_g="300",
    )

    response = await client.get(PANTRY_SUMMARY_URL, headers=headers)

    assert response.status_code == 200
    assert_summary_totals(
        response.json(),
        items_count=2,
        total_calories="720",
        total_protein_g="70.1",
        total_carbs_g="84",
        total_fat_g="8.1",
    )


@pytest.mark.asyncio
async def test_pantry_item_without_nutrition_value_contributes_zero(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_test_ingredient(
        client,
        name="Ingredient Without Nutrition",
        include_nutrition=False,
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=ingredient["id"],
        quantity_g="100",
    )

    response = await client.get(PANTRY_SUMMARY_URL, headers=headers)

    assert response.status_code == 200
    assert_summary_totals(
        response.json(),
        items_count=1,
        total_calories="0",
        total_protein_g="0",
        total_carbs_g="0",
        total_fat_g="0",
    )


@pytest.mark.asyncio
async def test_pantry_summary_uses_current_authenticated_user_only(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email="summary-first-user@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email="summary-second-user@example.com",
    )
    ingredient = await create_test_ingredient(client)

    await add_pantry_item(
        client,
        headers=first_headers,
        ingredient_id=ingredient["id"],
        quantity_g="100",
    )
    await add_pantry_item(
        client,
        headers=second_headers,
        ingredient_id=ingredient["id"],
        quantity_g="300",
    )

    response = await client.get(PANTRY_SUMMARY_URL, headers=first_headers)

    assert response.status_code == 200
    assert_summary_totals(
        response.json(),
        items_count=1,
        total_calories="389",
        total_protein_g="16.9",
        total_carbs_g="66.3",
        total_fat_g="6.9",
    )


@pytest.mark.asyncio
async def test_updating_pantry_item_quantity_changes_pantry_summary(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_test_ingredient(client)

    pantry_item = await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=ingredient["id"],
        quantity_g="100",
    )

    update_response = await client.patch(
        f"{PANTRY_URL}/{pantry_item['id']}",
        headers=headers,
        json={
            "quantity_g": "200",
        },
    )

    assert update_response.status_code == 200

    response = await client.get(PANTRY_SUMMARY_URL, headers=headers)

    assert response.status_code == 200
    assert_summary_totals(
        response.json(),
        items_count=1,
        total_calories="778",
        total_protein_g="33.8",
        total_carbs_g="132.6",
        total_fat_g="13.8",
    )


@pytest.mark.asyncio
async def test_updating_ingredient_nutrition_value_is_reflected_in_pantry_summary(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_test_ingredient(
        client,
        name="Dynamic Nutrition Ingredient",
        nutrition_value={
            "calories": "100",
            "protein_g": "10",
            "carbs_g": "5",
            "fat_g": "2",
            "portion_g": "100",
        },
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=ingredient["id"],
        quantity_g="150",
    )

    update_response = await client.patch(
        f"/api/v1/ingredients/{ingredient['id']}",
        json={
            "nutrition_value": {
                "calories": "200",
                "protein_g": "20",
                "carbs_g": "10",
                "fat_g": "4",
                "portion_g": "100",
            },
        },
    )

    assert update_response.status_code == 200

    response = await client.get(PANTRY_SUMMARY_URL, headers=headers)

    assert response.status_code == 200
    assert_summary_totals(
        response.json(),
        items_count=1,
        total_calories="300",
        total_protein_g="30",
        total_carbs_g="15",
        total_fat_g="6",
    )


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
