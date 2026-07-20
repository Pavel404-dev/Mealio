from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
)
from pydantic import ValidationError

from app.integrations.recipe_generation import (
    RecipeGenerationInvalidResponseError,
    RecipeGenerationTimeoutError,
    RecipeGenerationUnavailableError,
)
from app.schemas.ai_recipe import AIRecipeProviderRequest, GeneratedRecipeData

MAX_AI_RECIPE_OUTPUT_TOKENS = 2000


class OpenAIRecipeGenerationProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def generate_recipe(
        self,
        *,
        provider_request: AIRecipeProviderRequest,
    ) -> GeneratedRecipeData:
        try:
            async with AsyncOpenAI(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=0,
            ) as client:
                response = await client.responses.parse(
                    model=self.model,
                    instructions=provider_request.instructions,
                    input=provider_request.input,
                    text_format=GeneratedRecipeData,
                    max_output_tokens=MAX_AI_RECIPE_OUTPUT_TOKENS,
                )
        except APITimeoutError as exc:
            raise RecipeGenerationTimeoutError from exc
        except (APIConnectionError, APIStatusError) as exc:
            raise RecipeGenerationUnavailableError from exc
        except (
            ContentFilterFinishReasonError,
            LengthFinishReasonError,
            ValidationError,
        ) as exc:
            raise RecipeGenerationInvalidResponseError from exc

        if response.status in {"cancelled", "failed", "incomplete"}:
            raise RecipeGenerationInvalidResponseError

        parsed = response.output_parsed

        if parsed is None:
            raise RecipeGenerationInvalidResponseError

        try:
            return GeneratedRecipeData.model_validate(parsed)
        except ValidationError as exc:
            raise RecipeGenerationInvalidResponseError from exc
