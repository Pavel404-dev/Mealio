from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
INGREDIENTS_URL = "/api/v1/ingredients"
PANTRY_URL = "/api/v1/pantry"
RECIPES_URL = "/api/v1/recipes"
MEAL_PLANS_URL = "/api/v1/meal-plans"
SHOPPING_LIST_URL = "/api/v1/shopping-list"
ADD_MISSING_TO_PANTRY_URL = "/api/v1/shopping-list/add-missing-to-pantry"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"add-missing-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Add Missing User",
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
    category: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    if headers is None:
        _, headers = await create_authenticated_user(client)

    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={
            "name": name,
            "category": category,
            "nutrition_value": {
                "calories": "100",
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
) -> dict:
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": title,
            "instructions": "Cook and serve.",
            "diet_type": "balanced",
            "ingredients": ingredients,
        },
    )

    assert response.status_code == 201

    return response.json()


async def create_test_meal_plan(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str = "Add Missing Weekly Plan",
    start_date: str = "2026-05-18",
    end_date: str | None = "2026-05-24",
) -> dict:
    payload = {
        "title": title,
        "start_date": start_date,
    }

    if end_date is not None:
        payload["end_date"] = end_date

    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json=payload,
    )

    assert response.status_code == 201

    return response.json()


async def add_meal_plan_item(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    meal_plan_id: str,
    recipe_id: str,
    planned_date: str,
    meal_type: str,
) -> dict:
    response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan_id}/items",
        headers=headers,
        json={
            "recipe_id": recipe_id,
            "planned_date": planned_date,
            "meal_type": meal_type,
        },
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


async def get_current_user_pantry(
    client: AsyncClient,
    *,
    headers: dict[str, str],
) -> list[dict]:
    response = await client.get(PANTRY_URL, headers=headers)

    assert response.status_code == 200

    return response.json()


def decimal_value(value) -> Decimal:
    return Decimal(str(value))


def get_item_by_ingredient_id(
    data: list[dict],
    ingredient_id: str,
) -> dict:
    for item in data:
        if item["ingredient_id"] == ingredient_id:
            return item

    raise AssertionError(f"Ingredient {ingredient_id} not found")


@pytest.mark.asyncio
async def test_add_missing_to_empty_pantry_success(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Add Missing Empty Pantry Chicken {uuid4()}",
        category="meat",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Add Missing Empty Pantry Rice {uuid4()}",
        category="grain",
    )

    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Chicken Rice",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "900",
            },
            {
                "ingredient_id": rice["id"],
                "quantity_g": "100",
            },
        ],
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-05-18",
        meal_type="dinner",
    )

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["updated_items_count"] == 0
    assert data["added_items_count"] == 2
    assert data["skipped_items_count"] == 0
    assert len(data["items"]) == 2

    chicken_item = get_item_by_ingredient_id(data["items"], chicken["id"])
    rice_item = get_item_by_ingredient_id(data["items"], rice["id"])

    assert chicken_item["ingredient_name"] == chicken["name"]
    assert decimal_value(chicken_item["added_quantity_g"]) == Decimal("900")
    assert decimal_value(chicken_item["new_pantry_quantity_g"]) == Decimal("900")

    assert rice_item["ingredient_name"] == rice["name"]
    assert decimal_value(rice_item["added_quantity_g"]) == Decimal("100")
    assert decimal_value(rice_item["new_pantry_quantity_g"]) == Decimal("100")

    pantry = await get_current_user_pantry(client, headers=headers)
    pantry_chicken = get_item_by_ingredient_id(pantry, chicken["id"])
    pantry_rice = get_item_by_ingredient_id(pantry, rice["id"])

    assert decimal_value(pantry_chicken["quantity_g"]) == Decimal("900")
    assert decimal_value(pantry_rice["quantity_g"]) == Decimal("100")


@pytest.mark.asyncio
async def test_add_missing_increases_existing_pantry_item_quantity(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Add Missing Existing Pantry Chicken {uuid4()}",
        category="meat",
    )

    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Existing Pantry Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "900",
            }
        ],
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-05-18",
        meal_type="dinner",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="300",
    )

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["updated_items_count"] == 1
    assert data["added_items_count"] == 0
    assert data["skipped_items_count"] == 0
    assert len(data["items"]) == 1

    item = data["items"][0]

    assert item["ingredient_id"] == chicken["id"]
    assert decimal_value(item["added_quantity_g"]) == Decimal("600")
    assert decimal_value(item["new_pantry_quantity_g"]) == Decimal("900")

    pantry = await get_current_user_pantry(client, headers=headers)
    pantry_chicken = get_item_by_ingredient_id(pantry, chicken["id"])

    assert decimal_value(pantry_chicken["quantity_g"]) == Decimal("900")


@pytest.mark.asyncio
async def test_add_missing_skips_item_when_missing_quantity_is_zero(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Add Missing Skipped Chicken {uuid4()}",
        category="meat",
    )

    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Skipped Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "900",
            }
        ],
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-05-18",
        meal_type="dinner",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="1000",
    )

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["updated_items_count"] == 0
    assert data["added_items_count"] == 0
    assert data["skipped_items_count"] == 1
    assert data["items"] == []

    pantry = await get_current_user_pantry(client, headers=headers)
    pantry_chicken = get_item_by_ingredient_id(pantry, chicken["id"])

    assert decimal_value(pantry_chicken["quantity_g"]) == Decimal("1000")


@pytest.mark.asyncio
async def test_add_missing_groups_multiple_recipes_and_meal_plans_before_pantry_update(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Add Missing Grouped Chicken {uuid4()}",
        category="meat",
    )

    breakfast_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Breakfast Chicken",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "200",
            }
        ],
    )
    lunch_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Lunch Chicken",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "300",
            }
        ],
    )

    first_meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        title="Add Missing First Plan",
    )
    second_meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        title="Add Missing Second Plan",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=first_meal_plan["id"],
        recipe_id=breakfast_recipe["id"],
        planned_date="2026-05-18",
        meal_type="breakfast",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=second_meal_plan["id"],
        recipe_id=lunch_recipe["id"],
        planned_date="2026-05-19",
        meal_type="lunch",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="100",
    )

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-19",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["updated_items_count"] == 1
    assert data["added_items_count"] == 0
    assert data["skipped_items_count"] == 0
    assert len(data["items"]) == 1
    assert decimal_value(data["items"][0]["added_quantity_g"]) == Decimal("400")
    assert decimal_value(data["items"][0]["new_pantry_quantity_g"]) == Decimal("500")

    pantry = await get_current_user_pantry(client, headers=headers)
    pantry_chicken = get_item_by_ingredient_id(pantry, chicken["id"])

    assert decimal_value(pantry_chicken["quantity_g"]) == Decimal("500")


@pytest.mark.asyncio
async def test_add_missing_respects_date_range_filter(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Add Missing Date Chicken {uuid4()}",
        category="meat",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Add Missing Date Rice {uuid4()}",
        category="grain",
    )

    chicken_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Outside Date Chicken",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "300",
            }
        ],
    )
    rice_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Inside Date Rice",
        ingredients=[
            {
                "ingredient_id": rice["id"],
                "quantity_g": "500",
            }
        ],
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=chicken_recipe["id"],
        planned_date="2026-05-18",
        meal_type="dinner",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=rice_recipe["id"],
        planned_date="2026-05-20",
        meal_type="lunch",
    )

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-05-20",
            "to_date": "2026-05-20",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["added_items_count"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["ingredient_id"] == rice["id"]
    assert decimal_value(data["items"][0]["added_quantity_g"]) == Decimal("500")

    pantry = await get_current_user_pantry(client, headers=headers)

    assert get_item_by_ingredient_id(pantry, rice["id"])
    assert all(item["ingredient_id"] != chicken["id"] for item in pantry)


@pytest.mark.asyncio
async def test_add_missing_respects_meal_type_filter_case_insensitively(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Add Missing Meal Type Chicken {uuid4()}",
        category="meat",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Add Missing Meal Type Rice {uuid4()}",
        category="grain",
    )

    breakfast_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Breakfast Chicken",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "300",
            }
        ],
    )
    lunch_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Lunch Rice",
        ingredients=[
            {
                "ingredient_id": rice["id"],
                "quantity_g": "200",
            }
        ],
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=breakfast_recipe["id"],
        planned_date="2026-05-18",
        meal_type="breakfast",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=lunch_recipe["id"],
        planned_date="2026-05-18",
        meal_type="Lunch",
    )

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-18",
            "meal_type": "LuNcH",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["added_items_count"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["ingredient_id"] == rice["id"]

    pantry = await get_current_user_pantry(client, headers=headers)

    assert get_item_by_ingredient_id(pantry, rice["id"])
    assert all(item["ingredient_id"] != chicken["id"] for item in pantry)


@pytest.mark.asyncio
async def test_add_missing_empty_shopping_list_returns_zero_counts(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-06-01",
            "to_date": "2026-06-07",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "updated_items_count": 0,
        "added_items_count": 0,
        "skipped_items_count": 0,
        "items": [],
    }


@pytest.mark.asyncio
async def test_add_missing_cannot_update_another_users_pantry(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-add-missing-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-add-missing-user-{uuid4()}@example.com",
    )

    chicken = await create_test_ingredient(
        client,
        name=f"Add Missing Private Chicken {uuid4()}",
        category="meat",
    )

    recipe = await create_test_recipe(
        client,
        headers=first_headers,
        title="Add Missing First User Chicken",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "500",
            }
        ],
    )
    meal_plan = await create_test_meal_plan(client, headers=first_headers)

    await add_meal_plan_item(
        client,
        headers=first_headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-05-18",
        meal_type="dinner",
    )
    await add_pantry_item(
        client,
        headers=second_headers,
        ingredient_id=chicken["id"],
        quantity_g="100",
    )

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=first_headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
        },
    )

    assert response.status_code == 200

    first_pantry = await get_current_user_pantry(client, headers=first_headers)
    second_pantry = await get_current_user_pantry(client, headers=second_headers)

    first_chicken = get_item_by_ingredient_id(first_pantry, chicken["id"])
    second_chicken = get_item_by_ingredient_id(second_pantry, chicken["id"])

    assert decimal_value(first_chicken["quantity_g"]) == Decimal("500")
    assert decimal_value(second_chicken["quantity_g"]) == Decimal("100")


@pytest.mark.asyncio
async def test_add_missing_does_not_use_another_users_pantry_for_subtraction(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-add-missing-subtract-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-add-missing-subtract-user-{uuid4()}@example.com",
    )

    chicken = await create_test_ingredient(
        client,
        name=f"Add Missing Subtract Private Chicken {uuid4()}",
        category="meat",
    )

    recipe = await create_test_recipe(
        client,
        headers=first_headers,
        title="Add Missing Subtract First User Chicken",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "500",
            }
        ],
    )
    meal_plan = await create_test_meal_plan(client, headers=first_headers)

    await add_meal_plan_item(
        client,
        headers=first_headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-05-18",
        meal_type="dinner",
    )
    await add_pantry_item(
        client,
        headers=second_headers,
        ingredient_id=chicken["id"],
        quantity_g="300",
    )

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=first_headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["added_items_count"] == 1
    assert decimal_value(data["items"][0]["added_quantity_g"]) == Decimal("500")
    assert decimal_value(data["items"][0]["new_pantry_quantity_g"]) == Decimal("500")

    first_pantry = await get_current_user_pantry(client, headers=first_headers)
    second_pantry = await get_current_user_pantry(client, headers=second_headers)

    first_chicken = get_item_by_ingredient_id(first_pantry, chicken["id"])
    second_chicken = get_item_by_ingredient_id(second_pantry, chicken["id"])

    assert decimal_value(first_chicken["quantity_g"]) == Decimal("500")
    assert decimal_value(second_chicken["quantity_g"]) == Decimal("300")


@pytest.mark.asyncio
async def test_add_missing_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_add_missing_rejects_invalid_token(
    client: AsyncClient,
) -> None:
    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers={
            "Authorization": "Bearer invalid-token",
        },
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_add_missing_requires_from_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "to_date": "2026-05-24",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_add_missing_requires_to_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_add_missing_rejects_invalid_date_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-05-24",
            "to_date": "2026-05-18",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "from_date must be less than or equal to to_date"
    )


@pytest.mark.asyncio
async def test_add_missing_rejects_blank_meal_type(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        ADD_MISSING_TO_PANTRY_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
            "meal_type": "   ",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Meal type cannot be empty"


@pytest.mark.asyncio
async def test_existing_combined_shopping_list_endpoint_still_works(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Add Missing Regression Chicken {uuid4()}",
        category="meat",
    )

    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Add Missing Regression Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "250",
            }
        ],
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-05-18",
        meal_type="breakfast",
    )

    response = await client.get(
        SHOPPING_LIST_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["ingredient_id"] == chicken["id"]
    assert data[0]["ingredient_name"] == chicken["name"]
    assert decimal_value(data[0]["required_quantity_g"]) == Decimal("250")
    assert data[0]["pantry_quantity_g"] is None
    assert data[0]["missing_quantity_g"] is None
