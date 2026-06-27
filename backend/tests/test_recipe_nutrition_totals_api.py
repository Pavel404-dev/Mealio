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
    headers: dict[str, str] | None = None,
) -> dict:
    if headers is None:
        _, headers = await create_authenticated_user(client)

    payload = {
        "name": name,
        "category": "test",
    }

    if nutrition_value is not None:
        payload["nutrition_value"] = nutrition_value

    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
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

    assert "total_calories" in data
    assert "total_protein_g" in data
    assert "total_carbs_g" in data
    assert "total_fat_g" in data
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
async def test_client_provided_nutrition_totals_are_rejected_when_ingredients_are_provided(
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

    assert response.status_code == 422


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


@pytest.mark.asyncio
async def test_recipe_nutrition_totals_are_recalculated_when_ingredient_nutrition_value_is_updated(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        name=f"Recalc Chicken {uuid4()}",
        nutrition_value={
            "calories": "100",
            "protein_g": "10",
            "carbs_g": "5",
            "fat_g": "2",
            "portion_g": "100",
        },
    )

    create_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Recipe Using Updated Ingredient",
            "instructions": "Cook.",
            "ingredients": [
                {
                    "ingredient_id": ingredient["id"],
                    "quantity_g": "200",
                }
            ],
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    assert_decimal(create_response.json()["total_calories"], "200")
    assert_decimal(create_response.json()["total_protein_g"], "20")
    assert_decimal(create_response.json()["total_carbs_g"], "10")
    assert_decimal(create_response.json()["total_fat_g"], "4")

    update_ingredient_response = await client.patch(
        f"{INGREDIENTS_URL}/{ingredient['id']}",
        headers=headers,
        json={
            "nutrition_value": {
                "calories": "150",
                "protein_g": "20",
                "carbs_g": "10",
                "fat_g": "4",
                "portion_g": "100",
            }
        },
    )

    assert update_ingredient_response.status_code == 200

    recipe_response = await client.get(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
    )

    assert recipe_response.status_code == 200

    data = recipe_response.json()

    assert_decimal(data["total_calories"], "300")
    assert_decimal(data["total_protein_g"], "40")
    assert_decimal(data["total_carbs_g"], "20")
    assert_decimal(data["total_fat_g"], "8")


@pytest.mark.asyncio
async def test_ingredient_nutrition_update_recalculates_multiple_recipes_using_this_ingredient(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        name=f"Shared Ingredient {uuid4()}",
        nutrition_value={
            "calories": "100",
            "protein_g": "10",
            "carbs_g": "5",
            "fat_g": "2",
            "portion_g": "100",
        },
    )

    first_recipe_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "First Recipe With Shared Ingredient",
            "instructions": "Cook first recipe.",
            "ingredients": [
                {
                    "ingredient_id": ingredient["id"],
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert first_recipe_response.status_code == 201

    second_recipe_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Second Recipe With Shared Ingredient",
            "instructions": "Cook second recipe.",
            "ingredients": [
                {
                    "ingredient_id": ingredient["id"],
                    "quantity_g": "300",
                }
            ],
        },
    )

    assert second_recipe_response.status_code == 201

    first_recipe_id = first_recipe_response.json()["id"]
    second_recipe_id = second_recipe_response.json()["id"]

    update_ingredient_response = await client.patch(
        f"{INGREDIENTS_URL}/{ingredient['id']}",
        headers=headers,
        json={
            "nutrition_value": {
                "calories": "200",
                "protein_g": "30",
                "carbs_g": "10",
                "fat_g": "5",
                "portion_g": "100",
            }
        },
    )

    assert update_ingredient_response.status_code == 200

    first_recipe_get_response = await client.get(
        f"{RECIPES_URL}/{first_recipe_id}",
        headers=headers,
    )
    second_recipe_get_response = await client.get(
        f"{RECIPES_URL}/{second_recipe_id}",
        headers=headers,
    )

    assert first_recipe_get_response.status_code == 200
    assert second_recipe_get_response.status_code == 200

    first_recipe = first_recipe_get_response.json()
    second_recipe = second_recipe_get_response.json()

    assert_decimal(first_recipe["total_calories"], "200")
    assert_decimal(first_recipe["total_protein_g"], "30")
    assert_decimal(first_recipe["total_carbs_g"], "10")
    assert_decimal(first_recipe["total_fat_g"], "5")

    assert_decimal(second_recipe["total_calories"], "600")
    assert_decimal(second_recipe["total_protein_g"], "90")
    assert_decimal(second_recipe["total_carbs_g"], "30")
    assert_decimal(second_recipe["total_fat_g"], "15")


@pytest.mark.asyncio
async def test_ingredient_nutrition_update_does_not_affect_recipes_without_this_ingredient(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    updated_ingredient = await create_test_ingredient(
        client,
        name=f"Updated Ingredient {uuid4()}",
        nutrition_value={
            "calories": "100",
            "protein_g": "10",
            "carbs_g": "5",
            "fat_g": "2",
            "portion_g": "100",
        },
    )
    untouched_ingredient = await create_test_ingredient(
        client,
        name=f"Untouched Ingredient {uuid4()}",
        nutrition_value={
            "calories": "50",
            "protein_g": "5",
            "carbs_g": "10",
            "fat_g": "1",
            "portion_g": "100",
        },
    )

    affected_recipe_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Affected Recipe",
            "instructions": "Cook affected recipe.",
            "ingredients": [
                {
                    "ingredient_id": updated_ingredient["id"],
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert affected_recipe_response.status_code == 201

    unaffected_recipe_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Unaffected Recipe",
            "instructions": "Cook unaffected recipe.",
            "ingredients": [
                {
                    "ingredient_id": untouched_ingredient["id"],
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert unaffected_recipe_response.status_code == 201

    affected_recipe_id = affected_recipe_response.json()["id"]
    unaffected_recipe_id = unaffected_recipe_response.json()["id"]

    update_ingredient_response = await client.patch(
        f"{INGREDIENTS_URL}/{updated_ingredient['id']}",
        headers=headers,
        json={
            "nutrition_value": {
                "calories": "300",
                "protein_g": "40",
                "carbs_g": "15",
                "fat_g": "8",
                "portion_g": "100",
            }
        },
    )

    assert update_ingredient_response.status_code == 200

    affected_recipe_get_response = await client.get(
        f"{RECIPES_URL}/{affected_recipe_id}",
        headers=headers,
    )
    unaffected_recipe_get_response = await client.get(
        f"{RECIPES_URL}/{unaffected_recipe_id}",
        headers=headers,
    )

    assert affected_recipe_get_response.status_code == 200
    assert unaffected_recipe_get_response.status_code == 200

    affected_recipe = affected_recipe_get_response.json()
    unaffected_recipe = unaffected_recipe_get_response.json()

    assert_decimal(affected_recipe["total_calories"], "300")
    assert_decimal(affected_recipe["total_protein_g"], "40")
    assert_decimal(affected_recipe["total_carbs_g"], "15")
    assert_decimal(affected_recipe["total_fat_g"], "8")

    assert_decimal(unaffected_recipe["total_calories"], "50")
    assert_decimal(unaffected_recipe["total_protein_g"], "5")
    assert_decimal(unaffected_recipe["total_carbs_g"], "10")
    assert_decimal(unaffected_recipe["total_fat_g"], "1")
