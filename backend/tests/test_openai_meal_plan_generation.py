import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.integrations.meal_plan_generation import MealPlanProviderTimeout
from app.integrations.openai_meal_plan_generation import OpenAIMealPlanProvider
from app.schemas.ai_meal_plan import GeneratedMealPlanSelection


@pytest.fixture
def openai_client(monkeypatch):
    parse = AsyncMock()
    options = {}

    class Client:
        def __init__(self, **kwargs):
            options.update(kwargs)
            self.responses = SimpleNamespace(parse=parse)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(
        "app.integrations.openai_meal_plan_generation.AsyncOpenAI", Client
    )
    return parse, options


@pytest.mark.parametrize("status", ["completed", "incomplete"])
async def test_model_schema_usage_and_retention_options(openai_client, status):
    parse, options = openai_client
    output = {
        "items": [
            {"meal_type": "lunch", "candidate_number": 1, "serving_hundredths": 100}
        ]
    }
    parse.return_value = SimpleNamespace(
        status=status,
        output_parsed=output,
        usage=SimpleNamespace(input_tokens=15, output_tokens=10),
    )
    provider = OpenAIMealPlanProvider(
        api_key="test-key", model="test-model", timeout_seconds=1
    )
    result = await provider.select_meals(context_json='{"locale": "uk"}')
    assert result.selection == (output if status == "completed" else None)
    assert (result.input_tokens, result.output_tokens) == (15, 10)
    assert options == {"api_key": "test-key", "timeout": 1, "max_retries": 0}
    call = parse.call_args.kwargs
    assert call["text_format"] is GeneratedMealPlanSelection
    assert call["store"] is False and call["max_output_tokens"] == 1000
    assert call["input"] == '{"locale": "uk"}'


async def test_provider_deadline_cancels_stuck_request(openai_client):
    parse, _ = openai_client

    async def delayed(**kwargs):
        await asyncio.sleep(60)

    parse.side_effect = delayed
    provider = OpenAIMealPlanProvider(
        api_key="test-key", model="test-model", timeout_seconds=0.01
    )
    with pytest.raises(MealPlanProviderTimeout):
        await provider.select_meals(context_json="{}")
