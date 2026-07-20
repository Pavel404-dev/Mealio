from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_recipe_generation_provider
from app.core.config import get_settings
from app.integrations.recipe_generation import (
    RecipeGenerationInvalidResponseError,
    RecipeGenerationTimeoutError,
    RecipeGenerationUnavailableError,
)
from app.main import app
from app.models.ingredient import Ingredient, UserIngredient
from app.models.recipe import Recipe
from app.schemas.ai_recipe import (
    AIRecipeProviderRequest,
    GeneratedRecipeData,
    GeneratedRecipeIngredient,
    MAX_AI_PANTRY_ITEMS,
)

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
AI_RECIPE_PREVIEW_URL = "/api/v1/recipes/ai/generate-preview"
PANTRY_URL = "/api/v1/pantry"
NUTRITION_PROFILE_URL = "/api/v1/user-preferences/nutrition"


class FakeRecipeGenerationProvider:
    def __init__(self) -> None:
        self.result = GeneratedRecipeData(
            title="Chicken Rice Bowl",
            description="A practical generated dinner.",
            servings=2,
            prep_time_minutes=30,
            diet_type="balanced",
            ingredients=[
                GeneratedRecipeIngredient(
                    name="Chicken breast",
                    quantity="300",
                    unit="g",
                ),
                GeneratedRecipeIngredient(
                    name="Rice",
                    quantity="160",
                    unit="g",
                ),
            ],
            instructions=[
                "Cook the rice.",
                "Cook the chicken and serve.",
            ],
        )
        self.error: Exception | None = None
        self.calls: list[AIRecipeProviderRequest] = []

    async def generate_recipe(
        self,
        *,
        provider_request: AIRecipeProviderRequest,
    ) -> GeneratedRecipeData:
        self.calls.append(provider_request)

        if self.error is not None:
            raise self.error

        return self.result


@pytest.fixture
def fake_provider() -> FakeRecipeGenerationProvider:
    provider = FakeRecipeGenerationProvider()
    app.dependency_overrides[get_recipe_generation_provider] = lambda: provider

    yield provider

    app.dependency_overrides.pop(get_recipe_generation_provider, None)


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    email = email or f"ai-user-{uuid4()}@example.com"
    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "AI Recipe User",
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

    return register_response.json(), {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }


async def create_ingredient(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str,
) -> str:
    response = await client.post(
        "/api/v1/ingredients",
        headers=headers,
        json={
            "name": name,
            "category": "test",
            "nutrition_value": {
                "calories": "100",
                "protein_g": "10",
                "carbs_g": "10",
                "fat_g": "2",
                "portion_g": "100",
            },
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def add_pantry_item(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    ingredient_id: str,
    quantity_g: str,
) -> None:
    response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": ingredient_id,
            "quantity_g": quantity_g,
        },
    )
    assert response.status_code == 201


def generation_payload(**overrides) -> dict:
    payload = {
        "meal_type": "dinner",
        "servings": 2,
        "max_prep_time_minutes": 45,
        "use_only_pantry": False,
        "additional_preferences": "High protein and easy to cook",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_generate_ai_recipe_preview_success(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(),
    )

    assert response.status_code == 200
    parsed = GeneratedRecipeData.model_validate(response.json())
    assert parsed == fake_provider.result
    assert len(fake_provider.calls) == 1


@pytest.mark.asyncio
async def test_generate_ai_recipe_preview_requires_authentication(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        json=generation_payload(),
    )

    assert response.status_code == 401
    assert fake_provider.calls == []


@pytest.mark.asyncio
async def test_generation_context_uses_only_current_user_pantry(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    first_user, first_headers = await create_authenticated_user(client)
    _, second_headers = await create_authenticated_user(client)
    first_name = f"Current User Ingredient {uuid4()}"
    second_name = f"Other User Ingredient {uuid4()}"
    first_ingredient_id = await create_ingredient(
        client,
        headers=first_headers,
        name=first_name,
    )
    second_ingredient_id = await create_ingredient(
        client,
        headers=second_headers,
        name=second_name,
    )
    await add_pantry_item(
        client,
        headers=first_headers,
        ingredient_id=first_ingredient_id,
        quantity_g="250",
    )
    await add_pantry_item(
        client,
        headers=second_headers,
        ingredient_id=second_ingredient_id,
        quantity_g="400",
    )

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=first_headers,
        json=generation_payload(),
    )

    assert response.status_code == 200
    pantry_items = fake_provider.calls[-1].context.pantry_items
    assert [item.name for item in pantry_items] == [first_name]
    assert pantry_items[0].available_quantity_g == Decimal("250")
    provider_input = fake_provider.calls[-1].input
    assert second_name not in provider_input
    assert first_user["id"] not in provider_input
    assert first_user["email"] not in provider_input


@pytest.mark.asyncio
async def test_generation_context_includes_nutrition_profile_and_allergies(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)
    profile_response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={
            "goal": "gain_weight",
            "diet_type": "high-protein",
            "daily_calories_target": 2400,
            "daily_protein_target_g": 150,
            "daily_carbs_target_g": 300,
            "daily_fat_target_g": 90,
            "allergies": ["Peanuts"],
            "disliked_ingredients": ["Celery"],
            "preferred_meals_per_day": 3,
        },
    )
    assert profile_response.status_code == 200

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(),
    )

    assert response.status_code == 200
    profile = fake_provider.calls[-1].context.nutrition_profile
    assert profile.goal == "gain_weight"
    assert profile.diet_type == "high-protein"
    assert profile.allergies == ["Peanuts"]
    assert profile.disliked_ingredients == ["Celery"]
    assert profile.calories_target_per_meal == Decimal("800.00")
    assert profile.protein_target_per_meal_g == Decimal("50.00")
    assert "hard safety constraints" in fake_provider.calls[-1].instructions


@pytest.mark.asyncio
async def test_generation_uses_default_profile_when_profile_is_missing(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(),
    )

    assert response.status_code == 200
    profile = fake_provider.calls[-1].context.nutrition_profile
    assert profile.goal == "maintain"
    assert profile.diet_type == "balanced"
    assert profile.allergies == []
    assert profile.disliked_ingredients == []
    assert profile.preferred_meals_per_day == 3
    assert profile.calories_target_per_meal is None


@pytest.mark.asyncio
async def test_use_only_pantry_is_passed_and_enforced(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_name = f"Pantry Rice {uuid4()}"
    ingredient_id = await create_ingredient(
        client,
        headers=headers,
        name=ingredient_name,
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=ingredient_id,
        quantity_g="250",
    )
    fake_provider.result = GeneratedRecipeData(
        title="Pantry Rice",
        servings=2,
        prep_time_minutes=20,
        diet_type="balanced",
        ingredients=[
            GeneratedRecipeIngredient(
                name=ingredient_name,
                quantity="200",
                unit="g",
            )
        ],
        instructions=["Cook and serve."],
    )

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(use_only_pantry=True),
    )

    assert response.status_code == 200
    call = fake_provider.calls[-1]
    assert call.context.request.use_only_pantry is True
    assert "Use only pantry ingredients" in call.instructions


@pytest.mark.asyncio
async def test_empty_pantry_with_use_only_pantry_returns_422(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(use_only_pantry=True),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Pantry is empty; use_only_pantry cannot be true"
    )
    assert fake_provider.calls == []


@pytest.mark.asyncio
async def test_use_only_pantry_rejects_more_than_context_limit(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    user, headers = await create_authenticated_user(client)
    ingredients = [
        Ingredient(
            name=f"AI Pantry Limit Ingredient {index} {uuid4()}",
            category="test",
        )
        for index in range(MAX_AI_PANTRY_ITEMS + 1)
    ]
    db_session.add_all(ingredients)
    await db_session.flush()
    db_session.add_all(
        [
            UserIngredient(
                user_id=UUID(user["id"]),
                ingredient_id=ingredient.id,
                quantity_g=Decimal("100"),
            )
            for ingredient in ingredients
        ]
    )
    await db_session.commit()

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(use_only_pantry=True),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Pantry contains too many available items for pantry-only "
        f"generation; maximum is {MAX_AI_PANTRY_ITEMS}"
    )
    assert fake_provider.calls == []


@pytest.mark.asyncio
async def test_empty_pantry_is_allowed_when_not_restricted(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(use_only_pantry=False),
    )

    assert response.status_code == 200
    assert fake_provider.calls[-1].context.pantry_items == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"servings": 0},
        {"servings": 13},
        {"max_prep_time_minutes": 0},
        {"max_prep_time_minutes": 481},
        {"meal_type": "x" * 101},
        {"additional_preferences": "x" * 501},
        {"unexpected": "field"},
    ],
)
@pytest.mark.asyncio
async def test_generate_ai_recipe_preview_validates_request(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
    overrides: dict,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(**overrides),
    )

    assert response.status_code == 422
    assert fake_provider.calls == []


@pytest.mark.asyncio
async def test_generation_request_trims_optional_text(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(
            meal_type="  dinner  ",
            additional_preferences="  easy to cook  ",
        ),
    )

    assert response.status_code == 200
    request = fake_provider.calls[-1].context.request
    assert request.meal_type == "dinner"
    assert request.additional_preferences == "easy to cook"


@pytest.mark.asyncio
async def test_provider_timeout_returns_503(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)
    fake_provider.error = RecipeGenerationTimeoutError()

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "AI recipe generation timed out"


@pytest.mark.asyncio
async def test_provider_unavailable_returns_503(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)
    fake_provider.error = RecipeGenerationUnavailableError()

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "AI recipe generation is temporarily unavailable"
    )


@pytest.mark.asyncio
async def test_invalid_provider_response_returns_502(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)
    fake_provider.error = RecipeGenerationInvalidResponseError()

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(),
    )

    assert response.status_code == 502
    assert response.json()["detail"] == ("AI provider returned an invalid recipe")


@pytest.mark.asyncio
async def test_semantically_invalid_provider_response_returns_502(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)
    fake_provider.result = fake_provider.result.model_copy(update={"servings": 3})

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(servings=2),
    )

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_generated_recipe_cannot_directly_include_allergy(
    client: AsyncClient,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)
    profile_response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json={"allergies": ["Peanuts"]},
    )
    assert profile_response.status_code == 200
    fake_provider.result = fake_provider.result.model_copy(
        update={
            "ingredients": [
                GeneratedRecipeIngredient(
                    name="Roasted peanuts",
                    quantity="50",
                    unit="g",
                )
            ]
        }
    )

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(),
    )

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_missing_openai_api_key_returns_503(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await create_authenticated_user(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", None)

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == ("AI recipe generation is not configured")


@pytest.mark.asyncio
async def test_preview_does_not_create_recipes_or_ingredients(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_provider: FakeRecipeGenerationProvider,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(
        client,
        headers=headers,
        name=f"Existing Ingredient {uuid4()}",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=ingredient_id,
        quantity_g="200",
    )
    recipes_before = await db_session.scalar(select(func.count()).select_from(Recipe))
    ingredients_before = await db_session.scalar(
        select(func.count()).select_from(Ingredient)
    )

    response = await client.post(
        AI_RECIPE_PREVIEW_URL,
        headers=headers,
        json=generation_payload(),
    )

    assert response.status_code == 200
    recipes_after = await db_session.scalar(select(func.count()).select_from(Recipe))
    ingredients_after = await db_session.scalar(
        select(func.count()).select_from(Ingredient)
    )
    assert recipes_after == recipes_before
    assert ingredients_after == ingredients_before
