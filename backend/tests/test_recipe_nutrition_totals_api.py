from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
INGREDIENTS_URL = "/api/v1/ingredients"
RECIPES_URL = "/api/v1/recipes"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"recipe-nutrition-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Recipe Nutrition Test User",
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
    name: str,
    nutrition_value: dict | None,
) -> dict:
    payload = {
        "name": name,
        "category": "test",
    }

    if nutrition_value is not None:
        payload["nutrition_value"] = nutrition_value

    response = await client.post(
        INGREDIENTS_URL,
        json=payload,
    )

    assert response.status_code == 201

    return response.json()


def assert_decimal(value, expected: str) -> None:
    assert Decimal(str(value)) == Decimal(expected)


@pytest.mark.asyncio
async def test_recipe_nutrition_totals_are_calculated_from_one_ingredient(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        name=f"Chicken Breast {uuid4()}",
        nutrition_value={
            "calories": "165",
            "protein_g": "31",
            "carbs_g": "0",
            "fat_g": "3.6",
            "portion_g": "100",
        },
    )

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Chicken Recipe",
            "instructions": "Cook chicken.",
            "ingredients": [
                {
                    "ingredient_id": ingredient["id"],
                    "quantity_g": "200",
                }
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert_decimal(data["total_calories"], "330")
    assert_decimal(data["total_protein_g"], "62")
    assert_decimal(data["total_carbs_g"], "0")
    assert_decimal(data["total_fat_g"], "7.20")


@pytest.mark.asyncio
async def test_recipe_nutrition_totals_are_calculated_from_multiple_ingredients(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Chicken Breast {uuid4()}",
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
        name=f"Rice {uuid4()}",
        nutrition_value={
            "calories": "130",
            "protein_g": "2.7",
            "carbs_g": "28",
            "fat_g": "0.3",
            "portion_g": "100",
        },
    )

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Chicken Rice Bowl",
            "instructions": "Cook chicken and rice.",
            "ingredients": [
                {
                    "ingredient_id": chicken["id"],
                    "quantity_g": "200",
                },
                {
                    "ingredient_id": rice["id"],
                    "quantity_g": "150",
                },
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert_decimal(data["total_calories"], "525")
    assert_decimal(data["total_protein_g"], "66.05")
    assert_decimal(data["total_carbs_g"], "42")
    assert_decimal(data["total_fat_g"], "7.65")


@pytest.mark.asyncio
async def test_recipe_nutrition_totals_are_recalculated_when_ingredients_are_updated(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Update Chicken {uuid4()}",
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
        name=f"Update Rice {uuid4()}",
        nutrition_value={
            "calories": "130",
            "protein_g": "2.7",
            "carbs_g": "28",
            "fat_g": "0.3",
            "portion_g": "100",
        },
    )

    create_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Recipe To Update",
            "instructions": "Cook.",
            "ingredients": [
                {
                    "ingredient_id": chicken["id"],
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    update_response = await client.patch(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
        json={
            "ingredients": [
                {
                    "ingredient_id": rice["id"],
                    "quantity_g": "200",
                }
            ],
        },
    )

    assert update_response.status_code == 200

    data = update_response.json()

    assert_decimal(data["total_calories"], "260")
    assert_decimal(data["total_protein_g"], "5.40")
    assert_decimal(data["total_carbs_g"], "56")
    assert_decimal(data["total_fat_g"], "0.60")


@pytest.mark.asyncio
async def test_ingredient_without_nutrition_value_contributes_zero(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        name=f"No Nutrition Ingredient {uuid4()}",
        nutrition_value=None,
    )

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Zero Nutrition Recipe",
            "instructions": "Cook ingredient.",
            "ingredients": [
                {
                    "ingredient_id": ingredient["id"],
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert_decimal(data["total_calories"], "0")
    assert_decimal(data["total_protein_g"], "0")
    assert_decimal(data["total_carbs_g"], "0")
    assert_decimal(data["total_fat_g"], "0")


@pytest.mark.asyncio
async def test_client_provided_nutrition_totals_are_ignored_when_ingredients_are_provided(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        name=f"Client Totals Ingredient {uuid4()}",
        nutrition_value={
            "calories": "100",
            "protein_g": "10",
            "carbs_g": "20",
            "fat_g": "5",
            "portion_g": "100",
        },
    )

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Client Totals Recipe",
            "instructions": "Cook.",
            "total_calories": "999",
            "total_protein_g": "999",
            "total_carbs_g": "999",
            "total_fat_g": "999",
            "ingredients": [
                {
                    "ingredient_id": ingredient["id"],
                    "quantity_g": "50",
                }
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert_decimal(data["total_calories"], "50")
    assert_decimal(data["total_protein_g"], "5")
    assert_decimal(data["total_carbs_g"], "10")
    assert_decimal(data["total_fat_g"], "2.50")


@pytest.mark.asyncio
async def test_recipe_created_without_ingredients_has_zero_nutrition_totals(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Empty Recipe",
            "instructions": "Cook nothing.",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert_decimal(data["total_calories"], "0")
    assert_decimal(data["total_protein_g"], "0")
    assert_decimal(data["total_carbs_g"], "0")
    assert_decimal(data["total_fat_g"], "0")
