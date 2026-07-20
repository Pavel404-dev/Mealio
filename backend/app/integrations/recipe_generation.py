from typing import Protocol

from app.schemas.ai_recipe import AIRecipeProviderRequest, GeneratedRecipeData


class RecipeGenerationProviderError(Exception):
    pass


class RecipeGenerationTimeoutError(RecipeGenerationProviderError):
    pass


class RecipeGenerationUnavailableError(RecipeGenerationProviderError):
    pass


class RecipeGenerationInvalidResponseError(RecipeGenerationProviderError):
    pass


class RecipeGenerationProvider(Protocol):
    async def generate_recipe(
        self,
        *,
        provider_request: AIRecipeProviderRequest,
    ) -> GeneratedRecipeData: ...
