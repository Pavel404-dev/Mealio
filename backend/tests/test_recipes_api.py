from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
RECIPES_URL = "/api/v1/recipes"
MEAL_PLANS_URL = "/api/v1/meal-plans"

NUTRITION_TOTAL_FIELDS = (
    "total_calories",
    "total_protein_g",
    "total_carbs_g",
    "total_fat_g",
)


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"test-user-{uuid4()}@example.com"

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
    name: str = "Chicken Breast",
    calories: str = "165",
    protein_g: str = "31",
    carbs_g: str = "0",
    fat_g: str = "3.6",
    portion_g: str = "100",
) -> str:
    response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": name,
            "category": "protein",
            "nutrition_value": {
                "calories": calories,
                "protein_g": protein_g,
                "carbs_g": carbs_g,
                "fat_g": fat_g,
                "portion_g": portion_g,
            },
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


async def create_test_recipe(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str = "Test Recipe",
    description: str | None = None,
    instructions: str = "Cook and serve.",
    diet_type: str | None = None,
    ingredients: list[dict] | None = None,
) -> dict:
    payload = {
        "title": title,
        "instructions": instructions,
    }

    if description is not None:
        payload["description"] = description

    if diet_type is not None:
        payload["diet_type"] = diet_type

    if ingredients is not None:
        payload["ingredients"] = ingredients

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json=payload,
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_create_recipe_success(
    client: AsyncClient,
) -> None:
    user, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "High Protein Chicken Bowl",
            "description": "Simple protein meal",
            "instructions": "Cook chicken and serve with rice.",
            "diet_type": "high-protein",
            "ingredients": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "200",
                }
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["created_by_user_id"] == user["id"]
    assert data["title"] == "High Protein Chicken Bowl"
    assert data["diet_type"] == "high-protein"
    assert Decimal(str(data["total_calories"])) == Decimal("330")
    assert Decimal(str(data["total_protein_g"])) == Decimal("62")
    assert Decimal(str(data["total_carbs_g"])) == Decimal("0")
    assert Decimal(str(data["total_fat_g"])) == Decimal("7.20")
    assert len(data["recipe_ingredients"]) == 1
    assert data["recipe_ingredients"][0]["ingredient_id"] == ingredient_id


@pytest.mark.asyncio
async def test_create_recipe_rejects_client_created_by_user_id(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "created_by_user_id": str(uuid4()),
            "title": "Client Owned Recipe",
            "instructions": "Cook something.",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_rejects_blank_title(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "   ",
            "instructions": "Cook everything.",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_rejects_blank_instructions(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Simple Recipe",
            "instructions": "   ",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_normalizes_blank_optional_fields(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Simple Rice",
            "description": "   ",
            "instructions": "Boil rice.",
            "diet_type": "   ",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["description"] is None
    assert data["diet_type"] is None


@pytest.mark.asyncio
async def test_create_recipe_rejects_duplicate_ingredients(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Duplicate Ingredient Recipe",
            "instructions": "Cook ingredients.",
            "ingredients": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "100",
                },
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "200",
                },
            ],
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_rejects_non_positive_ingredient_quantity(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Invalid Quantity Recipe",
            "instructions": "Cook ingredients.",
            "ingredients": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "0",
                }
            ],
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize("field_name", NUTRITION_TOTAL_FIELDS)
@pytest.mark.asyncio
async def test_create_recipe_rejects_client_provided_nutrition_total(
    client: AsyncClient,
    field_name: str,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Client Nutrition Recipe",
            "instructions": "Cook something.",
            field_name: "100",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_recipe_rejects_null_required_fields(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    create_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Original Recipe",
            "instructions": "Original instructions.",
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    title_response = await client.patch(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
        json={
            "title": None,
        },
    )

    assert title_response.status_code == 422

    instructions_response = await client.patch(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
        json={
            "instructions": None,
        },
    )

    assert instructions_response.status_code == 422


@pytest.mark.parametrize("field_name", NUTRITION_TOTAL_FIELDS)
@pytest.mark.asyncio
async def test_update_recipe_rejects_client_provided_nutrition_total(
    client: AsyncClient,
    field_name: str,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Read Only Nutrition Recipe",
    )

    response = await client.patch(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=headers,
        json={
            field_name: "100",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_recipe_can_replace_existing_ingredient_quantity(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    create_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Chicken Bowl",
            "instructions": "Cook chicken.",
            "ingredients": [
                {
                    "ingredient_id": ingredient_id,
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
                    "ingredient_id": ingredient_id,
                    "quantity_g": "250",
                }
            ],
        },
    )

    assert update_response.status_code == 200

    data = update_response.json()

    assert len(data["recipe_ingredients"]) == 1
    assert data["recipe_ingredients"][0]["ingredient_id"] == ingredient_id
    assert Decimal(str(data["recipe_ingredients"][0]["quantity_g"])) == Decimal("250")


@pytest.mark.asyncio
async def test_create_recipe_rejects_missing_ingredient(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    missing_ingredient_id = uuid4()

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Missing Ingredient Recipe",
            "instructions": "Cook something.",
            "ingredients": [
                {
                    "ingredient_id": str(missing_ingredient_id),
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert response.status_code == 404
    assert "Ingredients not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_recipes_searches_by_title(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Fitness Bowl",
        instructions="Cook chicken.",
        diet_type="high-protein",
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Vegan Salad",
        instructions="Cut vegetables.",
        diet_type="vegan",
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "search": "Chicken",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Chicken Fitness Bowl"


@pytest.mark.asyncio
async def test_list_recipes_searches_by_description(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_recipe(
        client,
        headers=headers,
        title="Simple Bowl",
        description="Contains chicken and rice.",
        instructions="Cook everything.",
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Fruit Salad",
        description="Contains apples and bananas.",
        instructions="Cut fruit.",
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "search": "rice",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Simple Bowl"


@pytest.mark.asyncio
async def test_list_recipes_search_is_case_insensitive(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Fitness Bowl",
        instructions="Cook chicken.",
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Vegan Salad",
        instructions="Cut vegetables.",
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "search": "cHiCkEn",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Chicken Fitness Bowl"


@pytest.mark.asyncio
async def test_list_recipes_search_returns_empty_list(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Fitness Bowl",
        instructions="Cook chicken.",
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "search": "missing-recipe",
        },
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_recipes_filters_by_diet_type(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Bowl",
        instructions="Cook chicken.",
        diet_type="high-protein",
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Vegan Salad",
        instructions="Cut vegetables.",
        diet_type="vegan",
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "diet_type": "vegan",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Vegan Salad"
    assert data[0]["diet_type"] == "vegan"


@pytest.mark.asyncio
async def test_list_recipes_filters_by_min_calories(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    await create_test_recipe(
        client,
        headers=headers,
        title="Small Chicken Bowl",
        instructions="Cook chicken.",
        ingredients=[
            {
                "ingredient_id": ingredient_id,
                "quantity_g": "100",
            }
        ],
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Large Chicken Bowl",
        instructions="Cook more chicken.",
        ingredients=[
            {
                "ingredient_id": ingredient_id,
                "quantity_g": "300",
            }
        ],
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "min_calories": "400",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Large Chicken Bowl"
    assert Decimal(str(data[0]["total_calories"])) == Decimal("495")


@pytest.mark.asyncio
async def test_list_recipes_filters_by_max_calories(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    await create_test_recipe(
        client,
        headers=headers,
        title="Small Chicken Bowl",
        instructions="Cook chicken.",
        ingredients=[
            {
                "ingredient_id": ingredient_id,
                "quantity_g": "100",
            }
        ],
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Large Chicken Bowl",
        instructions="Cook more chicken.",
        ingredients=[
            {
                "ingredient_id": ingredient_id,
                "quantity_g": "300",
            }
        ],
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "max_calories": "200",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Small Chicken Bowl"
    assert Decimal(str(data[0]["total_calories"])) == Decimal("165")


@pytest.mark.asyncio
async def test_list_recipes_combines_search_diet_type_and_calories(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Fitness Bowl",
        description="High protein chicken meal.",
        instructions="Cook chicken.",
        diet_type="high-protein",
        ingredients=[
            {
                "ingredient_id": ingredient_id,
                "quantity_g": "200",
            }
        ],
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Light Salad",
        description="Light chicken meal.",
        instructions="Cut vegetables.",
        diet_type="low-calorie",
        ingredients=[
            {
                "ingredient_id": ingredient_id,
                "quantity_g": "50",
            }
        ],
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Vegan Fitness Bowl",
        description="Vegetable meal.",
        instructions="Cook vegetables.",
        diet_type="vegan",
        ingredients=[
            {
                "ingredient_id": ingredient_id,
                "quantity_g": "200",
            }
        ],
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "search": "chicken",
            "diet_type": "high-protein",
            "min_calories": "300",
            "max_calories": "400",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Chicken Fitness Bowl"
    assert data[0]["diet_type"] == "high-protein"
    assert Decimal(str(data[0]["total_calories"])) == Decimal("330")


@pytest.mark.asyncio
async def test_list_recipes_paginates_with_limit_and_offset(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_recipe(
        client,
        headers=headers,
        title="First Recipe",
        instructions="Cook first.",
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Second Recipe",
        instructions="Cook second.",
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Third Recipe",
        instructions="Cook third.",
    )

    first_page_response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "limit": 1,
            "offset": 0,
        },
    )
    second_page_response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "limit": 1,
            "offset": 1,
        },
    )

    assert first_page_response.status_code == 200
    assert second_page_response.status_code == 200

    first_page_data = first_page_response.json()
    second_page_data = second_page_response.json()

    assert len(first_page_data) == 1
    assert len(second_page_data) == 1
    assert first_page_data[0]["id"] != second_page_data[0]["id"]


@pytest.mark.asyncio
async def test_user_cannot_find_another_users_recipe_through_search(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-search-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-search-user-{uuid4()}@example.com",
    )

    await create_test_recipe(
        client,
        headers=first_headers,
        title="Private Chicken Recipe",
        instructions="Cook privately.",
    )

    response = await client.get(
        RECIPES_URL,
        headers=second_headers,
        params={
            "search": "Private Chicken",
        },
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_recipes_with_search_and_diet_type(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Chicken Fitness Bowl",
            "instructions": "Cook chicken.",
            "diet_type": "high-protein",
        },
    )

    await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Vegan Salad",
            "instructions": "Cut vegetables.",
            "diet_type": "vegan",
        },
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "search": "chicken",
            "diet_type": "high-protein",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Chicken Fitness Bowl"


@pytest.mark.asyncio
async def test_list_recipes_returns_only_current_users_recipes(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-list-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-list-user-{uuid4()}@example.com",
    )

    first_recipe_response = await client.post(
        RECIPES_URL,
        headers=first_headers,
        json={
            "title": "First User Chicken Bowl",
            "instructions": "Cook chicken.",
            "diet_type": "high-protein",
        },
    )

    assert first_recipe_response.status_code == 201

    second_recipe_response = await client.post(
        RECIPES_URL,
        headers=second_headers,
        json={
            "title": "Second User Vegan Salad",
            "instructions": "Cut vegetables.",
            "diet_type": "vegan",
        },
    )

    assert second_recipe_response.status_code == 201

    first_user_list_response = await client.get(
        RECIPES_URL,
        headers=first_headers,
    )

    assert first_user_list_response.status_code == 200

    first_user_recipes = first_user_list_response.json()

    assert len(first_user_recipes) == 1
    assert first_user_recipes[0]["title"] == "First User Chicken Bowl"

    second_user_list_response = await client.get(
        RECIPES_URL,
        headers=second_headers,
    )

    assert second_user_list_response.status_code == 200

    second_user_recipes = second_user_list_response.json()

    assert len(second_user_recipes) == 1
    assert second_user_recipes[0]["title"] == "Second User Vegan Salad"


@pytest.mark.asyncio
async def test_list_recipes_rejects_invalid_limit(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "limit": 0,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_recipes_rejects_too_large_limit(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "limit": 101,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_recipes_rejects_invalid_offset(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "offset": -1,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_recipes_rejects_negative_min_calories(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "min_calories": "-1",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_recipes_rejects_negative_max_calories(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "max_calories": "-1",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_recipes_rejects_min_calories_greater_than_max_calories(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "min_calories": "500",
            "max_calories": "100",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "min_calories must be less than or equal to max_calories"
    )


@pytest.mark.asyncio
async def test_get_update_and_delete_recipe(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    create_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Original Recipe",
            "instructions": "Original instructions.",
            "diet_type": "regular",
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    get_response = await client.get(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
    )

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Original Recipe"

    update_response = await client.patch(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
        json={
            "title": "Updated Recipe",
            "instructions": "Updated instructions.",
            "diet_type": "high-protein",
        },
    )

    assert update_response.status_code == 200

    updated_data = update_response.json()

    assert updated_data["title"] == "Updated Recipe"
    assert updated_data["instructions"] == "Updated instructions."
    assert updated_data["diet_type"] == "high-protein"
    assert Decimal(str(updated_data["total_calories"])) == Decimal("0")
    assert Decimal(str(updated_data["total_protein_g"])) == Decimal("0")
    assert Decimal(str(updated_data["total_carbs_g"])) == Decimal("0")
    assert Decimal(str(updated_data["total_fat_g"])) == Decimal("0")

    delete_response = await client.delete(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
    )

    assert delete_response.status_code == 204

    missing_response = await client.get(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
    )

    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_delete_own_recipe_used_in_meal_plan(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Meal Plan Recipe",
    )

    meal_plan_response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
            "items": [
                {
                    "recipe_id": recipe["id"],
                    "planned_date": "2026-05-18",
                    "meal_type": "breakfast",
                }
            ],
        },
    )

    assert meal_plan_response.status_code == 201

    delete_response = await client.delete(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=headers,
    )

    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == (
        "Recipe is used in meal plans and cannot be deleted"
    )

    get_response = await client.get(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=headers,
    )

    assert get_response.status_code == 200


@pytest.mark.asyncio
async def test_get_missing_recipe_returns_404(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    missing_id = uuid4()

    response = await client.get(
        f"{RECIPES_URL}/{missing_id}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found"


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    (
        ("GET", RECIPES_URL, {}),
        (
            "POST",
            RECIPES_URL,
            {
                "json": {
                    "title": "Auth Recipe",
                    "instructions": "Cook something.",
                }
            },
        ),
        ("GET", f"{RECIPES_URL}/{uuid4()}", {}),
        (
            "PATCH",
            f"{RECIPES_URL}/{uuid4()}",
            {
                "json": {
                    "title": "Updated Recipe",
                }
            },
        ),
        ("DELETE", f"{RECIPES_URL}/{uuid4()}", {}),
    ),
)
@pytest.mark.asyncio
async def test_recipe_endpoints_require_authentication(
    client: AsyncClient,
    method: str,
    url: str,
    kwargs: dict,
) -> None:
    response = await client.request(method, url, **kwargs)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    (
        ("GET", RECIPES_URL, {}),
        (
            "POST",
            RECIPES_URL,
            {
                "json": {
                    "title": "Auth Recipe",
                    "instructions": "Cook something.",
                }
            },
        ),
        ("GET", f"{RECIPES_URL}/{uuid4()}", {}),
        (
            "PATCH",
            f"{RECIPES_URL}/{uuid4()}",
            {
                "json": {
                    "title": "Updated Recipe",
                }
            },
        ),
        ("DELETE", f"{RECIPES_URL}/{uuid4()}", {}),
    ),
)
@pytest.mark.asyncio
async def test_recipe_endpoints_reject_invalid_token(
    client: AsyncClient,
    method: str,
    url: str,
    kwargs: dict,
) -> None:
    response = await client.request(
        method,
        url,
        headers={
            "Authorization": "Bearer invalid-token",
        },
        **kwargs,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_user_cannot_update_or_delete_another_users_recipe(
    client: AsyncClient,
) -> None:
    first_user, first_headers = await create_authenticated_user(
        client,
        email=f"first-recipe-user-{uuid4()}@example.com",
    )
    second_user, second_headers = await create_authenticated_user(
        client,
        email=f"second-recipe-user-{uuid4()}@example.com",
    )

    create_response = await client.post(
        RECIPES_URL,
        headers=first_headers,
        json={
            "title": "Private Recipe",
            "instructions": "Cook privately.",
        },
    )

    assert create_response.status_code == 201

    recipe = create_response.json()

    assert recipe["created_by_user_id"] == first_user["id"]
    assert recipe["created_by_user_id"] != second_user["id"]

    second_user_get_response = await client.get(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=second_headers,
    )

    assert second_user_get_response.status_code == 404
    assert second_user_get_response.json()["detail"] == "Recipe not found"

    second_user_update_response = await client.patch(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=second_headers,
        json={
            "title": "Hacked Recipe",
        },
    )

    assert second_user_update_response.status_code == 404
    assert second_user_update_response.json()["detail"] == "Recipe not found"

    second_user_delete_response = await client.delete(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=second_headers,
    )

    assert second_user_delete_response.status_code == 404
    assert second_user_delete_response.json()["detail"] == "Recipe not found"

    first_user_get_response = await client.get(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=first_headers,
    )

    assert first_user_get_response.status_code == 200
    assert first_user_get_response.json()["title"] == "Private Recipe"
