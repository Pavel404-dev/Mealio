from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def create_test_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"test-user-{uuid4()}@example.com",
        password_hash="test-password-hash",
        full_name="Test User",
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user


async def create_test_recipe(
    client: AsyncClient,
    title: str = "Chicken Bowl",
) -> str:
    response = await client.post(
        "/api/v1/recipes",
        json={
            "title": title,
            "instructions": "Cook and serve.",
            "diet_type": "high-protein",
            "total_calories": "550",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


async def create_test_meal_plan(
    client: AsyncClient,
    user_id: str,
) -> dict:
    response = await client.post(
        f"/api/v1/users/{user_id}/meal-plans",
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_create_meal_plan_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans",
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["user_id"] == str(user.id)
    assert data["title"] == "Weekly Meal Plan"
    assert data["start_date"] == "2026-05-18"
    assert data["end_date"] == "2026-05-24"
    assert data["items"] == []


@pytest.mark.asyncio
async def test_create_meal_plan_with_items_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    recipe_id = await create_test_recipe(client)

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans",
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
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    recipe_id = await create_test_recipe(client)

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans",
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
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    missing_recipe_id = uuid4()

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans",
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
async def test_create_meal_plan_rejects_duplicate_slots(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    recipe_id = await create_test_recipe(client)

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans",
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
async def test_create_meal_plan_rejects_missing_user(
    client: AsyncClient,
) -> None:
    missing_user_id = uuid4()

    response = await client.post(
        f"/api/v1/users/{missing_user_id}/meal-plans",
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_create_meal_plan_rejects_blank_title(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans",
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
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans",
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
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    meal_plan = await create_test_meal_plan(client, str(user.id))

    list_response = await client.get(f"/api/v1/users/{user.id}/meal-plans")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = await client.get(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}"
    )

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Weekly Meal Plan"

    update_response = await client.patch(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}",
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
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}"
    )

    assert delete_response.status_code == 204

    missing_response = await client.get(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}"
    )

    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Meal plan not found"


@pytest.mark.asyncio
async def test_add_meal_plan_item_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    recipe_id = await create_test_recipe(client)
    meal_plan = await create_test_meal_plan(client, str(user.id))

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items",
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
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    meal_plan = await create_test_meal_plan(client, str(user.id))
    missing_recipe_id = uuid4()

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items",
        json={
            "recipe_id": str(missing_recipe_id),
            "planned_date": "2026-05-18",
            "meal_type": "dinner",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found"


@pytest.mark.asyncio
async def test_add_meal_plan_item_rejects_date_outside_range(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    recipe_id = await create_test_recipe(client)
    meal_plan = await create_test_meal_plan(client, str(user.id))

    response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items",
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
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    recipe_id = await create_test_recipe(client)
    meal_plan = await create_test_meal_plan(client, str(user.id))

    payload = {
        "recipe_id": recipe_id,
        "planned_date": "2026-05-18",
        "meal_type": "breakfast",
    }

    first_response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items",
        json=payload,
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Meal plan already has an item for this date and meal type"
    )


@pytest.mark.asyncio
async def test_add_meal_plan_item_rejects_duplicate_slot_with_different_case(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    recipe_id = await create_test_recipe(client)
    meal_plan = await create_test_meal_plan(client, str(user.id))

    first_response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items",
        json={
            "recipe_id": recipe_id,
            "planned_date": "2026-05-18",
            "meal_type": "Lunch",
        },
    )

    assert first_response.status_code == 201
    assert first_response.json()["meal_type"] == "lunch"

    second_response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items",
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
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    recipe_id = await create_test_recipe(client, title="Chicken Bowl")
    second_recipe_id = await create_test_recipe(client, title="Rice Bowl")
    meal_plan = await create_test_meal_plan(client, str(user.id))

    create_item_response = await client.post(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items",
        json={
            "recipe_id": recipe_id,
            "planned_date": "2026-05-18",
            "meal_type": "lunch",
        },
    )

    assert create_item_response.status_code == 201

    item_id = create_item_response.json()["id"]

    update_response = await client.patch(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items/{item_id}",
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
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items/{item_id}"
    )

    assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_delete_missing_meal_plan_item_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    meal_plan = await create_test_meal_plan(client, str(user.id))
    missing_item_id = uuid4()

    response = await client.delete(
        f"/api/v1/users/{user.id}/meal-plans/{meal_plan['id']}/items/{missing_item_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Meal plan item not found"
