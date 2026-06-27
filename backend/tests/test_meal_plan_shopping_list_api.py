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


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"shopping-list-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Shopping List User",
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
    title: str = "Weekly Shopping Plan",
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


def decimal_value(value) -> Decimal:
    return Decimal(str(value))


def get_shopping_list_item_by_ingredient_id(
    data: list[dict],
    ingredient_id: str,
) -> dict:
    for item in data:
        if item["ingredient_id"] == ingredient_id:
            return item

    raise AssertionError(f"Ingredient {ingredient_id} not found in shopping list")


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_success(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Chicken Breast {uuid4()}",
        category="meat",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Rice {uuid4()}",
        category="grain",
    )

    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Rice Bowl",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "250",
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
        meal_type="breakfast",
    )

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert [item["ingredient_name"] for item in data] == sorted(
        [chicken["name"], rice["name"]]
    )

    chicken_item = get_shopping_list_item_by_ingredient_id(data, chicken["id"])
    rice_item = get_shopping_list_item_by_ingredient_id(data, rice["id"])

    assert chicken_item["ingredient_name"] == chicken["name"]
    assert chicken_item["ingredient_category"] == "meat"
    assert decimal_value(chicken_item["required_quantity_g"]) == Decimal("250")
    assert chicken_item["pantry_quantity_g"] is None
    assert chicken_item["missing_quantity_g"] is None

    assert rice_item["ingredient_name"] == rice["name"]
    assert rice_item["ingredient_category"] == "grain"
    assert decimal_value(rice_item["required_quantity_g"]) == Decimal("100")
    assert rice_item["pantry_quantity_g"] is None
    assert rice_item["missing_quantity_g"] is None


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_groups_same_ingredient_from_multiple_recipes(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Grouped Chicken {uuid4()}",
        category="meat",
    )

    breakfast_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Omelette",
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
        title="Chicken Salad",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "150",
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
        meal_type="lunch",
    )

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["ingredient_id"] == chicken["id"]
    assert decimal_value(data[0]["required_quantity_g"]) == Decimal("350")


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_filters_by_date_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Date Chicken {uuid4()}",
        category="meat",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Date Rice {uuid4()}",
        category="grain",
    )

    chicken_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Monday Chicken",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            }
        ],
    )
    rice_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Wednesday Rice",
        ingredients=[
            {
                "ingredient_id": rice["id"],
                "quantity_g": "300",
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
        meal_type="breakfast",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=rice_recipe["id"],
        planned_date="2026-05-20",
        meal_type="lunch",
    )

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
        headers=headers,
        params={
            "from_date": "2026-05-20",
            "to_date": "2026-05-20",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["ingredient_id"] == rice["id"]
    assert decimal_value(data[0]["required_quantity_g"]) == Decimal("300")


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_filters_by_meal_type_case_insensitive(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Meal Type Chicken {uuid4()}",
        category="meat",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Meal Type Rice {uuid4()}",
        category="grain",
    )

    breakfast_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Breakfast Chicken",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            }
        ],
    )
    lunch_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Lunch Rice",
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

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
        headers=headers,
        params={
            "meal_type": "LuNcH",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["ingredient_id"] == rice["id"]
    assert decimal_value(data[0]["required_quantity_g"]) == Decimal("200")


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_returns_empty_list_for_empty_meal_plan(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    meal_plan = await create_test_meal_plan(client, headers=headers)

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_current_user_cannot_access_another_users_meal_plan_shopping_list(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-shopping-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-shopping-user-{uuid4()}@example.com",
    )
    first_meal_plan = await create_test_meal_plan(client, headers=first_headers)

    response = await client.get(
        f"{MEAL_PLANS_URL}/{first_meal_plan['id']}/shopping-list",
        headers=second_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Meal plan not found"


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_returns_404_for_missing_meal_plan(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        f"{MEAL_PLANS_URL}/{uuid4()}/shopping-list",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Meal plan not found"


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{MEAL_PLANS_URL}/{uuid4()}/shopping-list",
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_rejects_invalid_token(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{MEAL_PLANS_URL}/{uuid4()}/shopping-list",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_rejects_invalid_date_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    meal_plan = await create_test_meal_plan(client, headers=headers)

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
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
async def test_get_meal_plan_shopping_list_subtract_pantry_false_returns_required_only(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Required Only Chicken {uuid4()}",
        category="meat",
    )
    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Required Only Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "750",
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
        quantity_g="200",
    )

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
        headers=headers,
        params={
            "subtract_pantry": "false",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert decimal_value(data[0]["required_quantity_g"]) == Decimal("750")
    assert data[0]["pantry_quantity_g"] is None
    assert data[0]["missing_quantity_g"] is None


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_subtract_pantry_true_subtracts_current_pantry(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Subtracted Chicken {uuid4()}",
        category="meat",
    )
    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Subtracted Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "750",
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
        quantity_g="200",
    )

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
        headers=headers,
        params={
            "subtract_pantry": "true",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert decimal_value(data[0]["required_quantity_g"]) == Decimal("750")
    assert decimal_value(data[0]["pantry_quantity_g"]) == Decimal("200")
    assert decimal_value(data[0]["missing_quantity_g"]) == Decimal("550")


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_subtract_pantry_does_not_use_another_users_pantry(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-pantry-owner-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-pantry-owner-{uuid4()}@example.com",
    )

    chicken = await create_test_ingredient(
        client,
        name=f"Private Pantry Chicken {uuid4()}",
        category="meat",
    )
    recipe = await create_test_recipe(
        client,
        headers=first_headers,
        title="Private Pantry Recipe",
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

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
        headers=first_headers,
        params={
            "subtract_pantry": "true",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert decimal_value(data[0]["required_quantity_g"]) == Decimal("500")
    assert decimal_value(data[0]["pantry_quantity_g"]) == Decimal("0")
    assert decimal_value(data[0]["missing_quantity_g"]) == Decimal("500")


@pytest.mark.asyncio
async def test_get_meal_plan_shopping_list_missing_quantity_never_goes_below_zero(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Enough Pantry Chicken {uuid4()}",
        category="meat",
    )
    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Enough Pantry Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "300",
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

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/shopping-list",
        headers=headers,
        params={
            "subtract_pantry": "true",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert decimal_value(data[0]["required_quantity_g"]) == Decimal("300")
    assert decimal_value(data[0]["pantry_quantity_g"]) == Decimal("1000")
    assert decimal_value(data[0]["missing_quantity_g"]) == Decimal("0")
