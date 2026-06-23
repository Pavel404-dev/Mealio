from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
MEAL_PLANS_URL = "/api/v1/meal-plans"


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
    title: str = "Chicken Bowl",
) -> str:
    response = await client.post(
        "/api/v1/recipes",
        headers=headers,
        json={
            "title": title,
            "instructions": "Cook and serve.",
            "diet_type": "high-protein",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


async def create_test_meal_plan(
    client: AsyncClient,
    headers: dict[str, str],
    *,
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


@pytest.mark.asyncio
async def test_create_meal_plan_success(
    client: AsyncClient,
) -> None:
    user, headers = await create_authenticated_user(client)

    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["user_id"] == user["id"]
    assert data["title"] == "Weekly Meal Plan"
    assert data["start_date"] == "2026-05-18"
    assert data["end_date"] == "2026-05-24"
    assert data["items"] == []


@pytest.mark.asyncio
async def test_create_meal_plan_with_items_success(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)

    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
            "items": [
                {
                    "recipe_id": recipe_id,
                    "planned_date": "2026-05-18",
                    "meal_type": "breakfast",
                }
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert len(data["items"]) == 1
    assert data["items"][0]["recipe_id"] == recipe_id
    assert data["items"][0]["planned_date"] == "2026-05-18"
    assert data["items"][0]["meal_type"] == "breakfast"


@pytest.mark.asyncio
async def test_create_meal_plan_with_items_rejects_date_outside_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)

    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
            "items": [
                {
                    "recipe_id": recipe_id,
                    "planned_date": "2026-05-30",
                    "meal_type": "dinner",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Planned date cannot be later than meal plan end date"
    )


@pytest.mark.asyncio
async def test_create_meal_plan_with_items_rejects_missing_recipe(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    missing_recipe_id = uuid4()

    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
            "items": [
                {
                    "recipe_id": str(missing_recipe_id),
                    "planned_date": "2026-05-18",
                    "meal_type": "dinner",
                }
            ],
        },
    )

    assert response.status_code == 404
    assert "Recipes not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_user_cannot_create_meal_plan_with_another_users_recipe(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-recipe-owner-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-meal-plan-owner-{uuid4()}@example.com",
    )

    another_users_recipe_id = await create_test_recipe(
        client,
        headers=first_headers,
    )

    response = await client.post(
        MEAL_PLANS_URL,
        headers=second_headers,
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
            "items": [
                {
                    "recipe_id": another_users_recipe_id,
                    "planned_date": "2026-05-18",
                    "meal_type": "breakfast",
                }
            ],
        },
    )

    assert response.status_code == 404
    assert "Recipes not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_meal_plan_rejects_duplicate_slots(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)

    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
            "items": [
                {
                    "recipe_id": recipe_id,
                    "planned_date": "2026-05-18",
                    "meal_type": "Lunch",
                },
                {
                    "recipe_id": recipe_id,
                    "planned_date": "2026-05-18",
                    "meal_type": "lunch",
                },
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Meal plan cannot contain duplicate meal slots"
    )


@pytest.mark.asyncio
async def test_create_meal_plan_rejects_blank_title(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "   ",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_meal_plan_rejects_invalid_date_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "Invalid Meal Plan",
            "start_date": "2026-05-24",
            "end_date": "2026-05-18",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_get_update_and_delete_meal_plan(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    meal_plan = await create_test_meal_plan(client, headers)

    list_response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
    )

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}",
        headers=headers,
    )

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Weekly Meal Plan"

    update_response = await client.patch(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}",
        headers=headers,
        json={
            "title": "Updated Meal Plan",
            "end_date": "2026-05-25",
        },
    )

    assert update_response.status_code == 200

    updated_data = update_response.json()

    assert updated_data["title"] == "Updated Meal Plan"
    assert updated_data["end_date"] == "2026-05-25"

    delete_response = await client.delete(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}",
        headers=headers,
    )

    assert delete_response.status_code == 204

    missing_response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}",
        headers=headers,
    )

    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Meal plan not found"


@pytest.mark.asyncio
async def test_list_meal_plans_searches_by_title(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_meal_plan(
        client,
        headers,
        title="Fitness Weekly Plan",
        start_date="2026-05-18",
        end_date="2026-05-24",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="Study Meal Plan",
        start_date="2026-05-25",
        end_date="2026-05-31",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "search": "Fitness",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Fitness Weekly Plan"


@pytest.mark.asyncio
async def test_list_meal_plans_search_is_case_insensitive(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_meal_plan(
        client,
        headers,
        title="Fitness Weekly Plan",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="Study Meal Plan",
        start_date="2026-05-25",
        end_date="2026-05-31",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "search": "fItNeSs",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Fitness Weekly Plan"


@pytest.mark.asyncio
async def test_list_meal_plans_search_returns_empty_list(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_meal_plan(
        client,
        headers,
        title="Fitness Weekly Plan",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "search": "missing-plan",
        },
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_meal_plans_filters_by_from_date_only(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_meal_plan(
        client,
        headers,
        title="Past Plan",
        start_date="2026-05-01",
        end_date="2026-05-07",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="Future Plan",
        start_date="2026-05-25",
        end_date="2026-05-31",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-21",
        },
    )

    assert response.status_code == 200

    titles = {item["title"] for item in response.json()}

    assert titles == {"Future Plan"}


@pytest.mark.asyncio
async def test_list_meal_plans_filters_by_to_date_only(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_meal_plan(
        client,
        headers,
        title="Past Plan",
        start_date="2026-05-01",
        end_date="2026-05-07",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="Current Plan",
        start_date="2026-05-10",
        end_date="2026-05-20",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "to_date": "2026-05-09",
        },
    )

    assert response.status_code == 200

    titles = {item["title"] for item in response.json()}

    assert titles == {"Past Plan"}


@pytest.mark.asyncio
async def test_list_meal_plans_filters_by_overlapping_date_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_meal_plan(
        client,
        headers,
        title="Past Plan",
        start_date="2026-05-01",
        end_date="2026-05-07",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="Current Plan",
        start_date="2026-05-10",
        end_date="2026-05-20",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="Future Plan",
        start_date="2026-05-25",
        end_date="2026-05-31",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "from_date": "2026-05-06",
            "to_date": "2026-05-12",
        },
    )

    assert response.status_code == 200

    titles = {item["title"] for item in response.json()}

    assert titles == {"Past Plan", "Current Plan"}


@pytest.mark.asyncio
async def test_list_meal_plans_date_filter_returns_empty_list_when_no_overlap(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_meal_plan(
        client,
        headers,
        title="May Plan",
        start_date="2026-05-01",
        end_date="2026-05-07",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "from_date": "2026-06-01",
            "to_date": "2026-06-05",
        },
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_meal_plans_combines_search_and_date_filters(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_meal_plan(
        client,
        headers,
        title="Fitness May Plan",
        start_date="2026-05-18",
        end_date="2026-05-24",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="Fitness June Plan",
        start_date="2026-06-01",
        end_date="2026-06-07",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="Study May Plan",
        start_date="2026-05-18",
        end_date="2026-05-24",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "search": "Fitness",
            "from_date": "2026-05-20",
            "to_date": "2026-05-21",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Fitness May Plan"


@pytest.mark.asyncio
async def test_list_meal_plans_pagination_with_limit_and_offset(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_meal_plan(
        client,
        headers,
        title="Old Plan",
        start_date="2026-05-01",
        end_date="2026-05-07",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="Middle Plan",
        start_date="2026-05-08",
        end_date="2026-05-14",
    )
    await create_test_meal_plan(
        client,
        headers,
        title="New Plan",
        start_date="2026-05-15",
        end_date="2026-05-21",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "limit": 1,
            "offset": 1,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Middle Plan"


@pytest.mark.asyncio
async def test_current_user_sees_only_own_filtered_meal_plans(
    client: AsyncClient,
) -> None:
    first_user, first_headers = await create_authenticated_user(
        client,
        email=f"first-filter-user-{uuid4()}@example.com",
    )
    second_user, second_headers = await create_authenticated_user(
        client,
        email=f"second-filter-user-{uuid4()}@example.com",
    )

    await create_test_meal_plan(
        client,
        first_headers,
        title="Shared Title Plan",
        start_date="2026-05-18",
        end_date="2026-05-24",
    )
    await create_test_meal_plan(
        client,
        second_headers,
        title="Shared Title Plan",
        start_date="2026-05-18",
        end_date="2026-05-24",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=second_headers,
        params={
            "search": "Shared",
            "from_date": "2026-05-20",
            "to_date": "2026-05-21",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["user_id"] == second_user["id"]
    assert data[0]["user_id"] != first_user["id"]


@pytest.mark.asyncio
async def test_user_cannot_find_another_users_meal_plan_through_search(
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

    await create_test_meal_plan(
        client,
        first_headers,
        title="Secret Other User Plan",
        start_date="2026-05-18",
        end_date="2026-05-24",
    )

    response = await client.get(
        MEAL_PLANS_URL,
        headers=second_headers,
        params={
            "search": "Secret",
        },
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_meal_plans_rejects_invalid_limit(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "limit": 0,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_meal_plans_rejects_invalid_offset(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLANS_URL,
        headers=headers,
        params={
            "offset": -1,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_meal_plans_rejects_from_date_greater_than_to_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        MEAL_PLANS_URL,
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
async def test_add_meal_plan_item_success(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)
    meal_plan = await create_test_meal_plan(client, headers)

    response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=headers,
        json={
            "recipe_id": recipe_id,
            "planned_date": "2026-05-18",
            "meal_type": "lunch",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["meal_plan_id"] == meal_plan["id"]
    assert data["recipe_id"] == recipe_id
    assert data["planned_date"] == "2026-05-18"
    assert data["meal_type"] == "lunch"


@pytest.mark.asyncio
async def test_add_meal_plan_item_rejects_missing_recipe(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    meal_plan = await create_test_meal_plan(client, headers)
    missing_recipe_id = uuid4()

    response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=headers,
        json={
            "recipe_id": str(missing_recipe_id),
            "planned_date": "2026-05-18",
            "meal_type": "dinner",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found"


@pytest.mark.asyncio
async def test_user_cannot_add_meal_plan_item_with_another_users_recipe(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-add-item-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-add-item-user-{uuid4()}@example.com",
    )

    another_users_recipe_id = await create_test_recipe(
        client,
        headers=first_headers,
    )
    meal_plan = await create_test_meal_plan(client, second_headers)

    response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=second_headers,
        json={
            "recipe_id": another_users_recipe_id,
            "planned_date": "2026-05-18",
            "meal_type": "lunch",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found"


@pytest.mark.asyncio
async def test_add_meal_plan_item_rejects_date_outside_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)
    meal_plan = await create_test_meal_plan(client, headers)

    response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=headers,
        json={
            "recipe_id": recipe_id,
            "planned_date": "2026-05-30",
            "meal_type": "dinner",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Planned date cannot be later than meal plan end date"
    )


@pytest.mark.asyncio
async def test_add_meal_plan_item_rejects_duplicate_slot(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)
    meal_plan = await create_test_meal_plan(client, headers)

    payload = {
        "recipe_id": recipe_id,
        "planned_date": "2026-05-18",
        "meal_type": "breakfast",
    }

    first_response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=headers,
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=headers,
        json=payload,
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Meal plan already has an item for this date and meal type"
    )


@pytest.mark.asyncio
async def test_add_meal_plan_item_rejects_duplicate_slot_with_different_case(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)
    meal_plan = await create_test_meal_plan(client, headers)

    first_response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=headers,
        json={
            "recipe_id": recipe_id,
            "planned_date": "2026-05-18",
            "meal_type": "Lunch",
        },
    )

    assert first_response.status_code == 201
    assert first_response.json()["meal_type"] == "lunch"

    second_response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=headers,
        json={
            "recipe_id": recipe_id,
            "planned_date": "2026-05-18",
            "meal_type": "lunch",
        },
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Meal plan already has an item for this date and meal type"
    )


@pytest.mark.asyncio
async def test_update_and_delete_meal_plan_item(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Bowl",
    )
    second_recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Rice Bowl",
    )
    meal_plan = await create_test_meal_plan(client, headers)

    create_item_response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=headers,
        json={
            "recipe_id": recipe_id,
            "planned_date": "2026-05-18",
            "meal_type": "lunch",
        },
    )

    assert create_item_response.status_code == 201

    item_id = create_item_response.json()["id"]

    update_response = await client.patch(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items/{item_id}",
        headers=headers,
        json={
            "recipe_id": second_recipe_id,
            "planned_date": "2026-05-19",
            "meal_type": "dinner",
        },
    )

    assert update_response.status_code == 200

    updated_data = update_response.json()

    assert updated_data["recipe_id"] == second_recipe_id
    assert updated_data["planned_date"] == "2026-05-19"
    assert updated_data["meal_type"] == "dinner"

    delete_response = await client.delete(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items/{item_id}",
        headers=headers,
    )

    assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_user_cannot_update_meal_plan_item_to_another_users_recipe(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-update-item-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-update-item-user-{uuid4()}@example.com",
    )

    another_users_recipe_id = await create_test_recipe(
        client,
        headers=first_headers,
        title="Another User Recipe",
    )
    own_recipe_id = await create_test_recipe(
        client,
        headers=second_headers,
        title="Own Recipe",
    )
    meal_plan = await create_test_meal_plan(client, second_headers)

    create_item_response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=second_headers,
        json={
            "recipe_id": own_recipe_id,
            "planned_date": "2026-05-18",
            "meal_type": "lunch",
        },
    )

    assert create_item_response.status_code == 201

    item_id = create_item_response.json()["id"]

    response = await client.patch(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items/{item_id}",
        headers=second_headers,
        json={
            "recipe_id": another_users_recipe_id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found"


@pytest.mark.asyncio
async def test_delete_missing_meal_plan_item_returns_404(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    meal_plan = await create_test_meal_plan(client, headers)
    missing_item_id = uuid4()

    response = await client.delete(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items/{missing_item_id}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Meal plan item not found"


@pytest.mark.asyncio
async def test_meal_plans_require_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(MEAL_PLANS_URL)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_meal_plans_reject_invalid_token(
    client: AsyncClient,
) -> None:
    response = await client.get(
        MEAL_PLANS_URL,
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_meal_plan(
    client: AsyncClient,
) -> None:
    first_user, first_headers = await create_authenticated_user(
        client,
        email=f"first-user-{uuid4()}@example.com",
    )
    second_user, second_headers = await create_authenticated_user(
        client,
        email=f"second-user-{uuid4()}@example.com",
    )

    meal_plan = await create_test_meal_plan(client, first_headers)

    assert meal_plan["user_id"] == first_user["id"]
    assert meal_plan["user_id"] != second_user["id"]

    second_user_list_response = await client.get(
        MEAL_PLANS_URL,
        headers=second_headers,
    )

    assert second_user_list_response.status_code == 200
    assert second_user_list_response.json() == []

    second_user_get_response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}",
        headers=second_headers,
    )

    assert second_user_get_response.status_code == 404
    assert second_user_get_response.json()["detail"] == "Meal plan not found"

    second_user_update_response = await client.patch(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}",
        headers=second_headers,
        json={
            "title": "Hacked Meal Plan",
        },
    )

    assert second_user_update_response.status_code == 404
    assert second_user_update_response.json()["detail"] == "Meal plan not found"

    second_user_delete_response = await client.delete(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}",
        headers=second_headers,
    )

    assert second_user_delete_response.status_code == 404
    assert second_user_delete_response.json()["detail"] == "Meal plan not found"


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_meal_plan_item(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-item-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-item-user-{uuid4()}@example.com",
    )

    recipe_id = await create_test_recipe(client, headers=first_headers)
    meal_plan = await create_test_meal_plan(client, first_headers)

    create_item_response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items",
        headers=first_headers,
        json={
            "recipe_id": recipe_id,
            "planned_date": "2026-05-18",
            "meal_type": "lunch",
        },
    )

    assert create_item_response.status_code == 201

    item_id = create_item_response.json()["id"]

    second_user_update_response = await client.patch(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items/{item_id}",
        headers=second_headers,
        json={
            "meal_type": "dinner",
        },
    )

    assert second_user_update_response.status_code == 404
    assert second_user_update_response.json()["detail"] == "Meal plan not found"

    second_user_delete_response = await client.delete(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/items/{item_id}",
        headers=second_headers,
    )

    assert second_user_delete_response.status_code == 404
    assert second_user_delete_response.json()["detail"] == "Meal plan not found"
