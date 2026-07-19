from types import SimpleNamespace

import pytest

from app.integrations.openai_recipe_generation import (
    OpenAIRecipeGenerationProvider,
)
from app.integrations.recipe_generation import (
    RecipeGenerationInvalidResponseError,
)
from app.schemas.ai_recipe import (
    AIRecipeGenerationContext,
    AIRecipeGenerationRequest,
    AIRecipeNutritionProfileContext,
    AIRecipeProviderRequest,
)


class FakeResponses:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeAsyncOpenAI:
    init_kwargs: dict | None = None
    responses_instance: FakeResponses | None = None

    def __init__(self, **kwargs) -> None:
        type(self).init_kwargs = kwargs
        self.responses = type(self).responses_instance

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def provider_request() -> AIRecipeProviderRequest:
    context = AIRecipeGenerationContext(
        request=AIRecipeGenerationRequest(servings=2),
        pantry_items=[],
        nutrition_profile=AIRecipeNutritionProfileContext(
            goal="maintain",
            diet_type="balanced",
            preferred_meals_per_day=3,
        ),
    )
    return AIRecipeProviderRequest(
        instructions="Generate one structured recipe.",
        input="Mealio context",
        context=context,
    )


@pytest.mark.asyncio
async def test_openai_provider_uses_async_structured_output_without_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        status="completed",
        output_parsed={
            "title": "Rice Bowl",
            "description": None,
            "servings": 2,
            "prep_time_minutes": 20,
            "diet_type": "balanced",
            "ingredients": [
                {
                    "name": "Rice",
                    "quantity": "160",
                    "unit": "g",
                }
            ],
            "instructions": ["Cook the rice."],
        },
    )
    responses = FakeResponses(response)
    FakeAsyncOpenAI.responses_instance = responses
    monkeypatch.setattr(
        "app.integrations.openai_recipe_generation.AsyncOpenAI",
        FakeAsyncOpenAI,
    )
    provider = OpenAIRecipeGenerationProvider(
        api_key="test-key",
        model="test-model",
        timeout_seconds=15,
    )

    result = await provider.generate_recipe(
        provider_request=provider_request(),
    )

    assert result.title == "Rice Bowl"
    assert FakeAsyncOpenAI.init_kwargs == {
        "api_key": "test-key",
        "timeout": 15,
        "max_retries": 0,
    }
    assert responses.calls[0]["model"] == "test-model"
    assert responses.calls[0]["text_format"].__name__ == "GeneratedRecipeData"
    assert responses.calls[0]["max_output_tokens"] == 2000


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(status="incomplete", output_parsed=None),
        SimpleNamespace(status="completed", output_parsed=None),
        SimpleNamespace(
            status="completed",
            output_parsed={
                "title": "",
                "servings": 2,
                "prep_time_minutes": 20,
                "ingredients": [],
                "instructions": [],
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_openai_provider_rejects_malformed_structured_response(
    monkeypatch: pytest.MonkeyPatch,
    response,
) -> None:
    FakeAsyncOpenAI.responses_instance = FakeResponses(response)
    monkeypatch.setattr(
        "app.integrations.openai_recipe_generation.AsyncOpenAI",
        FakeAsyncOpenAI,
    )
    provider = OpenAIRecipeGenerationProvider(
        api_key="test-key",
        model="test-model",
        timeout_seconds=15,
    )

    with pytest.raises(RecipeGenerationInvalidResponseError):
        await provider.generate_recipe(
            provider_request=provider_request(),
        )
