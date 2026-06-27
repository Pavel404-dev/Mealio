from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
INGREDIENTS_URL = "/api/v1/ingredients"
PANTRY_URL = "/api/v1/pantry"
RECIPES_URL = "/api/v1/recipes"
SUGGESTIONS_URL = f"{RECIPES_URL}/suggestions/from-pantry"
NUTRITION_PROFILE_URL = "/api/v1/user-preferences/nutrition"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"personalized-suggestion-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Personalized Suggestion User",
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
    headers: dict[str, str],
    name: str,
    category: str | None = None,
    calories: str = "100",
) -> dict:
    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={
            "name": name,
            "category": category,
            "nutrition_value": {
                "calories": calories,
                "protein_g": "10",
                "carbs_g": "5",
                "fat_g": "2",
                "portion_g": "100",
            },
        },
    )

    assert response.status_code == 201

    return response.json()


async def create_test_recipe(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str,
    ingredients: list[dict[str, str]],
    diet_type: str | None = "balanced",
) -> dict:
    payload = {
        "title": title,
        "instructions": "Cook and serve.",
        "ingredients": ingredients,
    }

    if diet_type is not None:
        payload["diet_type"] = diet_type

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json=payload,
    )

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


async def update_nutrition_profile(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    payload: dict,
) -> dict:
    response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json=payload,
    )

    assert response.status_code == 200

    return response.json()


def decimal_value(value) -> Decimal:
    return Decimal(str(value))


@pytest.mark.asyncio
async def test_personalized_recipe_suggestions_work_without_nutrition_profile(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        headers=headers,
        name=f"No Profile Chicken {uuid4()}",
    )

    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="No Profile Chicken Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="100",
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["recipe_id"] == recipe["id"]
    assert data[0]["recipe_title"] == "No Profile Chicken Recipe"


@pytest.mark.asyncio
async def test_personalized_recipe_suggestions_exclude_allergy_ingredients_case_insensitive(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    allergy_name = f"Personalized Peanuts {uuid4()}"
    allergy_profile_value = f"  {allergy_name.upper()}  "

    await update_nutrition_profile(
        client,
        headers=headers,
        payload={
            "allergies": [allergy_profile_value],
        },
    )

    chicken = await create_test_ingredient(
        client,
        headers=headers,
        name=f"Allergy Safe Chicken {uuid4()}",
    )
    peanuts = await create_test_ingredient(
        client,
        headers=headers,
        name=allergy_name,
    )

    allowed_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Allergy Safe Chicken Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
        ],
    )
    excluded_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Allergy Peanut Recipe",
        ingredients=[
            {
                "ingredient_id": peanuts["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="100",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=peanuts["id"],
        quantity_g="100",
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()
    recipe_ids = [item["recipe_id"] for item in data]

    assert recipe_ids == [allowed_recipe["id"]]
    assert excluded_recipe["id"] not in recipe_ids


@pytest.mark.asyncio
async def test_personalized_recipe_suggestions_exclude_disliked_ingredients_case_insensitive(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    disliked_name = f"Personalized Mushrooms {uuid4()}"
    disliked_profile_value = f"  {disliked_name.upper()}  "

    await update_nutrition_profile(
        client,
        headers=headers,
        payload={
            "disliked_ingredients": [disliked_profile_value],
        },
    )

    rice = await create_test_ingredient(
        client,
        headers=headers,
        name=f"Disliked Safe Rice {uuid4()}",
    )
    mushrooms = await create_test_ingredient(
        client,
        headers=headers,
        name=disliked_name,
    )

    allowed_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Disliked Safe Rice Recipe",
        ingredients=[
            {
                "ingredient_id": rice["id"],
                "quantity_g": "100",
            },
        ],
    )
    excluded_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Disliked Mushroom Recipe",
        ingredients=[
            {
                "ingredient_id": mushrooms["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=rice["id"],
        quantity_g="100",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=mushrooms["id"],
        quantity_g="100",
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()
    recipe_ids = [item["recipe_id"] for item in data]

    assert recipe_ids == [allowed_recipe["id"]]
    assert excluded_recipe["id"] not in recipe_ids


@pytest.mark.asyncio
async def test_personalized_recipe_suggestions_do_not_use_another_users_profile(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-personalized-suggestions-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-personalized-suggestions-user-{uuid4()}@example.com",
    )

    allergy_name = f"Other User Allergy Peanuts {uuid4()}"

    await update_nutrition_profile(
        client,
        headers=first_headers,
        payload={
            "allergies": [allergy_name],
        },
    )

    peanuts = await create_test_ingredient(
        client,
        headers=second_headers,
        name=allergy_name,
    )

    second_user_recipe = await create_test_recipe(
        client,
        headers=second_headers,
        title="Second User Peanut Recipe",
        ingredients=[
            {
                "ingredient_id": peanuts["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=second_headers,
        ingredient_id=peanuts["id"],
        quantity_g="100",
    )

    response = await client.get(SUGGESTIONS_URL, headers=second_headers)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["recipe_id"] == second_user_recipe["id"]


@pytest.mark.asyncio
async def test_personalized_recipe_suggestions_rank_matching_diet_type_first(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await update_nutrition_profile(
        client,
        headers=headers,
        payload={
            "diet_type": "high_protein",
        },
    )

    egg = await create_test_ingredient(
        client,
        headers=headers,
        name=f"Profile Diet Egg {uuid4()}",
    )

    balanced_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Balanced Profile Diet Recipe",
        diet_type="balanced",
        ingredients=[
            {
                "ingredient_id": egg["id"],
                "quantity_g": "100",
            },
        ],
    )
    high_protein_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="High Protein Profile Diet Recipe",
        diet_type="high_protein",
        ingredients=[
            {
                "ingredient_id": egg["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=egg["id"],
        quantity_g="100",
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert [item["recipe_id"] for item in data] == [
        high_protein_recipe["id"],
        balanced_recipe["id"],
    ]


@pytest.mark.asyncio
async def test_personalized_recipe_suggestions_rank_closer_calories_per_meal_first(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await update_nutrition_profile(
        client,
        headers=headers,
        payload={
            "daily_calories_target": 2400,
            "preferred_meals_per_day": 3,
        },
    )

    target_calories_ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name=f"Target Calories Ingredient {uuid4()}",
        calories="800",
    )
    low_calories_ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name=f"Low Calories Ingredient {uuid4()}",
        calories="600",
    )
    high_calories_ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name=f"High Calories Ingredient {uuid4()}",
        calories="1100",
    )

    target_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Zulu Target Calories Recipe",
        ingredients=[
            {
                "ingredient_id": target_calories_ingredient["id"],
                "quantity_g": "100",
            },
        ],
    )
    low_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Alpha Low Calories Recipe",
        ingredients=[
            {
                "ingredient_id": low_calories_ingredient["id"],
                "quantity_g": "100",
            },
        ],
    )
    high_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Bravo High Calories Recipe",
        ingredients=[
            {
                "ingredient_id": high_calories_ingredient["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=target_calories_ingredient["id"],
        quantity_g="100",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=low_calories_ingredient["id"],
        quantity_g="100",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=high_calories_ingredient["id"],
        quantity_g="100",
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert [item["recipe_id"] for item in data] == [
        target_recipe["id"],
        low_recipe["id"],
        high_recipe["id"],
    ]
    assert decimal_value(data[0]["total_calories"]) == Decimal("800")
    assert decimal_value(data[1]["total_calories"]) == Decimal("600")
    assert decimal_value(data[2]["total_calories"]) == Decimal("1100")
