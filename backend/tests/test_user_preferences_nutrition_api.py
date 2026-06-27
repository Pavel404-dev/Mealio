from uuid import uuid4

import pytest
from httpx import AsyncClient

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
NUTRITION_PROFILE_URL = "/api/v1/user-preferences/nutrition"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
    full_name: str = "Nutrition Profile User",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"nutrition-profile-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": full_name,
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


def assert_default_profile(profile: dict) -> None:
    assert profile["goal"] == "maintain"
    assert profile["diet_type"] == "balanced"
    assert profile["daily_calories_target"] is None
    assert profile["daily_protein_target_g"] is None
    assert profile["daily_carbs_target_g"] is None
    assert profile["daily_fat_target_g"] is None
    assert profile["allergies"] == []
    assert profile["disliked_ingredients"] == []
    assert profile["preferred_meals_per_day"] == 3


@pytest.mark.asyncio
async def test_unauthenticated_get_nutrition_profile_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get(NUTRITION_PROFILE_URL)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_patch_nutrition_profile_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.patch(
        NUTRITION_PROFILE_URL,
        json={
            "goal": "maintain",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_get_nutrition_profile_returns_default_profile(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        NUTRITION_PROFILE_URL,
        headers=headers,
    )

    assert response.status_code == 200
    assert_default_profile(response.json())


@pytest.mark.asyncio
async def test_patch_creates_nutrition_profile_if_it_does_not_exist(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={
            "goal": "gain_weight",
            "diet_type": "high_protein",
            "daily_calories_target": 3000,
            "daily_protein_target_g": 180,
            "daily_carbs_target_g": 350,
            "daily_fat_target_g": 90,
            "allergies": ["peanuts"],
            "disliked_ingredients": ["mushrooms"],
            "preferred_meals_per_day": 4,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["goal"] == "gain_weight"
    assert data["diet_type"] == "high_protein"
    assert data["daily_calories_target"] == 3000
    assert data["daily_protein_target_g"] == 180
    assert data["daily_carbs_target_g"] == 350
    assert data["daily_fat_target_g"] == 90
    assert data["allergies"] == ["peanuts"]
    assert data["disliked_ingredients"] == ["mushrooms"]
    assert data["preferred_meals_per_day"] == 4


@pytest.mark.asyncio
async def test_patch_updates_existing_nutrition_profile(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    create_response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={
            "goal": "maintain",
            "diet_type": "balanced",
            "daily_calories_target": 2500,
            "daily_protein_target_g": 140,
            "daily_carbs_target_g": 300,
            "daily_fat_target_g": 80,
            "allergies": ["peanuts"],
            "disliked_ingredients": ["mushrooms"],
            "preferred_meals_per_day": 3,
        },
    )

    assert create_response.status_code == 200

    update_response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={
            "goal": "lose_weight",
            "daily_calories_target": 2200,
            "allergies": ["shellfish"],
            "preferred_meals_per_day": 5,
        },
    )

    assert update_response.status_code == 200

    data = update_response.json()

    assert data["goal"] == "lose_weight"
    assert data["diet_type"] == "balanced"
    assert data["daily_calories_target"] == 2200
    assert data["daily_protein_target_g"] == 140
    assert data["daily_carbs_target_g"] == 300
    assert data["daily_fat_target_g"] == 80
    assert data["allergies"] == ["shellfish"]
    assert data["disliked_ingredients"] == ["mushrooms"]
    assert data["preferred_meals_per_day"] == 5


@pytest.mark.asyncio
async def test_user_cannot_see_or_update_another_users_nutrition_profile(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-nutrition-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-nutrition-user-{uuid4()}@example.com",
    )

    first_patch_response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=first_headers,
        json={
            "goal": "lose_weight",
            "diet_type": "low_carb",
            "daily_calories_target": 2100,
            "allergies": ["peanuts"],
            "disliked_ingredients": ["mushrooms"],
        },
    )

    assert first_patch_response.status_code == 200

    second_get_response = await client.get(
        NUTRITION_PROFILE_URL,
        headers=second_headers,
    )

    assert second_get_response.status_code == 200
    assert_default_profile(second_get_response.json())

    second_patch_response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=second_headers,
        json={
            "goal": "gain_weight",
            "diet_type": "balanced",
            "daily_calories_target": 3200,
            "allergies": ["milk"],
        },
    )

    assert second_patch_response.status_code == 200

    first_get_response = await client.get(
        NUTRITION_PROFILE_URL,
        headers=first_headers,
    )

    assert first_get_response.status_code == 200

    first_profile = first_get_response.json()

    assert first_profile["goal"] == "lose_weight"
    assert first_profile["diet_type"] == "low_carb"
    assert first_profile["daily_calories_target"] == 2100
    assert first_profile["allergies"] == ["peanuts"]
    assert first_profile["disliked_ingredients"] == ["mushrooms"]


@pytest.mark.asyncio
async def test_patch_rejects_invalid_goal(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={
            "goal": "bulk",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field_name",
    [
        "daily_calories_target",
        "daily_protein_target_g",
        "daily_carbs_target_g",
        "daily_fat_target_g",
    ],
)
async def test_patch_rejects_negative_numeric_targets(
    client: AsyncClient,
    field_name: str,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={
            field_name: -1,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preferred_meals_per_day",
    [
        0,
        9,
    ],
)
async def test_patch_rejects_invalid_preferred_meals_per_day(
    client: AsyncClient,
    preferred_meals_per_day: int,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={
            "preferred_meals_per_day": preferred_meals_per_day,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_normalizes_blank_diet_type_to_null(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={
            "diet_type": "   ",
        },
    )

    assert response.status_code == 200
    assert response.json()["diet_type"] is None


@pytest.mark.asyncio
async def test_patch_removes_blank_values_from_allergies_and_disliked_ingredients(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={
            "allergies": [
                " peanuts ",
                "",
                "   ",
                "milk",
            ],
            "disliked_ingredients": [
                " mushrooms ",
                "",
                "   ",
                "onion",
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["allergies"] == ["peanuts", "milk"]
    assert data["disliked_ingredients"] == ["mushrooms", "onion"]
