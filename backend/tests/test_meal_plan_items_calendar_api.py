from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
RECIPES_URL = "/api/v1/recipes"
MEAL_PLANS_URL = "/api/v1/meal-plans"
MEAL_PLAN_ITEMS_URL = "/api/v1/meal-plan-items"


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


async def create_test_recipe(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str,
) -> str:
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": title,
            "instructions": "Cook and serve.",
            "diet_type": "balanced",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


async def create_test_meal_plan(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str = "Weekly Meal Plan",
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


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_calendar_success(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    breakfast_recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Breakfast Bowl",
    )
    lunch_recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Rice",
    )
    dinner_recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Salmon Dinner",
    )

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        title="May Fitness Plan",
    )

    breakfast_item = await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=breakfast_recipe_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )
    lunch_item = await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=lunch_recipe_id,
        planned_date="2026-05-18",
        meal_type="lunch",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=dinner_recipe_id,
        planned_date="2026-05-20",
        meal_type="dinner",
    )

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-18",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data == [
        {
            "id": breakfast_item["id"],
            "meal_plan_id": meal_plan["id"],
            "meal_plan_title": "May Fitness Plan",
            "recipe_id": breakfast_recipe_id,
            "recipe_title": "Breakfast Bowl",
            "planned_date": "2026-05-18",
            "meal_type": "breakfast",
        },
        {
            "id": lunch_item["id"],
            "meal_plan_id": meal_plan["id"],
            "meal_plan_title": "May Fitness Plan",
            "recipe_id": lunch_recipe_id,
            "recipe_title": "Chicken Rice",
            "planned_date": "2026-05-18",
            "meal_type": "lunch",
        },
    ]


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_filters_by_date_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Bowl",
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )
    expected_item = await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-20",
        meal_type="lunch",
    )

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-20",
            "to_date": "2026-05-20",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == expected_item["id"]
    assert data[0]["planned_date"] == "2026-05-20"


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_filters_by_meal_type_case_insensitive(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Bowl",
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )
    lunch_item = await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-18",
        meal_type="Lunch",
    )

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-18",
            "meal_type": "LuNcH",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == lunch_item["id"]
    assert data[0]["meal_type"] == "lunch"


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_returns_empty_list_when_no_results(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-06-01",
            "to_date": "2026-06-07",
        },
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_pagination_with_limit_and_offset(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Bowl",
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )
    lunch_item = await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-18",
        meal_type="lunch",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-19",
        meal_type="dinner",
    )

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-19",
            "limit": 1,
            "offset": 1,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == lunch_item["id"]


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_are_sorted_for_calendar(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Bowl",
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-19",
        meal_type="dinner",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-18",
        meal_type="lunch",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-19",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert [(item["planned_date"], item["meal_type"]) for item in data] == [
        ("2026-05-18", "breakfast"),
        ("2026-05-18", "lunch"),
        ("2026-05-19", "dinner"),
    ]


@pytest.mark.asyncio
async def test_current_user_sees_only_own_meal_plan_items_calendar(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-calendar-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-calendar-user-{uuid4()}@example.com",
    )

    first_recipe_id = await create_test_recipe(
        client,
        headers=first_headers,
        title="First User Recipe",
    )
    second_recipe_id = await create_test_recipe(
        client,
        headers=second_headers,
        title="Second User Recipe",
    )

    first_meal_plan = await create_test_meal_plan(
        client,
        headers=first_headers,
        title="First User Plan",
    )
    second_meal_plan = await create_test_meal_plan(
        client,
        headers=second_headers,
        title="Second User Plan",
    )

    await add_meal_plan_item(
        client,
        headers=first_headers,
        meal_plan_id=first_meal_plan["id"],
        recipe_id=first_recipe_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )
    second_item = await add_meal_plan_item(
        client,
        headers=second_headers,
        meal_plan_id=second_meal_plan["id"],
        recipe_id=second_recipe_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=second_headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-18",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == second_item["id"]
    assert data[0]["meal_plan_id"] == second_meal_plan["id"]
    assert data[0]["meal_plan_title"] == "Second User Plan"


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_rejects_from_date_greater_than_to_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-06-10",
            "to_date": "2026-06-01",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "from_date must be less than or equal to to_date"
    )


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_rejects_blank_meal_type(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-18",
            "meal_type": "   ",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Meal type cannot be empty"


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_requires_from_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "to_date": "2026-05-18",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_requires_to_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_rejects_invalid_limit(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-18",
            "limit": 0,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_rejects_invalid_offset(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-18",
            "offset": -1,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-18",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_current_user_meal_plan_items_rejects_invalid_token(
    client: AsyncClient,
) -> None:
    response = await client.get(
        MEAL_PLAN_ITEMS_URL,
        headers={
            "Authorization": "Bearer invalid-token",
        },
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-18",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
