import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import Request, Response
from openai import APIConnectionError, APIStatusError, APITimeoutError, omit
from openai.types.responses import ResponseUsage
from openai.types.responses.response_usage import InputTokensDetails

from app.api.deps import (
    get_meal_plan_generation_provider,
    get_recipe_generation_provider,
)
from app.core.config import Settings
from app.integrations.meal_plan_generation import (
    MealPlanProviderTimeout,
    MealPlanProviderTransientError,
    MealPlanProviderUnavailable,
)
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
async def test_model_schema_usage_and_retention_options(
    openai_client, monkeypatch, status
):
    parse, options = openai_client
    output = {
        "items": [
            {"meal_type": "lunch", "candidate_number": 1, "serving_hundredths": 100}
        ]
    }
    parse.return_value = SimpleNamespace(
        status=status,
        output_parsed=output,
        service_tier="default",
        usage=SimpleNamespace(input_tokens=15, output_tokens=10),
    )
    settings = Settings(
        _env_file=None,
        openai_api_key="test-key",
        openai_meal_plan_api_key=None,
        openai_meal_plan_model="test-model",
        openai_meal_plan_reasoning_effort=None,
        ai_request_timeout_seconds=1,
    )
    monkeypatch.setattr("app.api.deps.get_settings", lambda: settings)
    provider = get_meal_plan_generation_provider()
    result = await provider.select_meals(context_json='{"locale": "uk"}')
    assert result.selection == (output if status == "completed" else None)
    assert (result.input_tokens, result.output_tokens) == (15, 10)
    assert result.estimated_cost_usd is None
    assert options == {"api_key": "test-key", "timeout": 1, "max_retries": 0}
    call = parse.call_args.kwargs
    assert call["model"] == "test-model" and call["reasoning"] is omit
    assert call["text_format"] is GeneratedMealPlanSelection
    assert call["store"] is False and call["max_output_tokens"] == 1000
    assert call["input"] == '{"locale": "uk"}'


@pytest.mark.parametrize("common_key", [None, "test-common-key"])
async def test_luna_uses_plan_key_and_low_reasoning(
    openai_client, monkeypatch, common_key
):
    parse, options = openai_client
    parse.return_value = SimpleNamespace(
        status="completed", output_parsed=None, service_tier="default", usage=None
    )
    monkeypatch.setenv("OPENAI_MEAL_PLAN_API_KEY", "test-plan-key")
    monkeypatch.setenv("OPENAI_MEAL_PLAN_MODEL", "gpt-6-luna")
    monkeypatch.setenv("OPENAI_MEAL_PLAN_REASONING_EFFORT", "low")
    settings = Settings(_env_file=None, openai_api_key=common_key)
    monkeypatch.setattr("app.api.deps.get_settings", lambda: settings)

    result = await get_meal_plan_generation_provider().select_meals(context_json="{}")
    assert result.estimated_cost_usd is None
    assert options["api_key"] == "test-plan-key"
    assert parse.call_args.kwargs["model"] == "gpt-6-luna"
    assert parse.call_args.kwargs["reasoning"] == {"effort": "low"}
    if common_key is None:
        with pytest.raises(HTTPException) as error:
            get_recipe_generation_provider()
        assert error.value.status_code == 503


@pytest.mark.parametrize(
    ("usage", "service_tier", "expected_cost"),
    [
        pytest.param(
            ResponseUsage.model_construct(input_tokens=410, output_tokens=34),
            None,
            Decimal("0.000058"),
            id="observed-staging-usage",
        ),
        pytest.param(
            ResponseUsage.model_construct(
                input_tokens=1600,
                output_tokens=34,
                input_tokens_details=InputTokensDetails(
                    cached_tokens=1100, cache_write_tokens=100
                ),
            ),
            "default",
            Decimal("0.0000805"),
            id="cache-reads-and-writes",
        ),
        pytest.param(
            ResponseUsage.model_construct(input_tokens=410),
            "default",
            None,
            id="missing-output-count",
        ),
        pytest.param(
            ResponseUsage.model_construct(input_tokens=1600, output_tokens=34),
            "default",
            None,
            id="missing-cache-breakdown",
        ),
        pytest.param(
            ResponseUsage.model_construct(
                input_tokens=1600,
                output_tokens=34,
                input_tokens_details=InputTokensDetails(
                    cached_tokens=1500, cache_write_tokens=200
                ),
            ),
            "default",
            None,
            id="inconsistent-cache-counts",
        ),
        pytest.param(
            ResponseUsage.model_construct(input_tokens=410, output_tokens=34),
            "flex",
            None,
            id="non-standard-tier",
        ),
        pytest.param(
            ResponseUsage.model_construct(input_tokens=272_001, output_tokens=34),
            "default",
            None,
            id="long-context-pricing",
        ),
    ],
)
async def test_luna_estimates_cost_from_returned_usage(
    openai_client, usage, service_tier, expected_cost
):
    parse, _ = openai_client
    parse.return_value = SimpleNamespace(
        status="completed", output_parsed=None, service_tier=service_tier, usage=usage
    )
    provider = OpenAIMealPlanProvider(
        api_key="test-key", model="gpt-6-luna", timeout_seconds=1
    )

    result = await provider.select_meals(context_json="{}")

    assert result.estimated_cost_usd == expected_cost


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


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        ("connection", MealPlanProviderTransientError),
        (503, MealPlanProviderTransientError),
        (401, MealPlanProviderUnavailable),
        (429, MealPlanProviderUnavailable),
        ("timeout", MealPlanProviderTimeout),
    ],
)
async def test_provider_classifies_failures_without_retrying(
    openai_client, failure, expected_error
):
    parse, _ = openai_client
    request = Request("POST", "https://api.example.test/responses")
    if failure == "connection":
        parse.side_effect = APIConnectionError(request=request)
    elif failure == "timeout":
        parse.side_effect = APITimeoutError(request)
    else:
        parse.side_effect = APIStatusError(
            "Private upstream message",
            response=Response(failure, request=request),
            body=None,
        )
    provider = OpenAIMealPlanProvider(
        api_key="test-key", model="test-model", timeout_seconds=1
    )

    with pytest.raises(expected_error) as error:
        await provider.select_meals(context_json="{}")

    assert type(error.value) is expected_error
    parse.assert_awaited_once()
