import re
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.recipe_generation import (
    RecipeGenerationInvalidResponseError,
    RecipeGenerationProvider,
    RecipeGenerationTimeoutError,
    RecipeGenerationUnavailableError,
)
from app.repositories.pantry import PantryRepository
from app.repositories.user_nutrition_profiles import UserNutritionProfilesRepository
from app.schemas.ai_recipe import (
    AIRecipeGenerationRequest,
    AIRecipePantryItemContext,
    GeneratedRecipeData,
    MAX_AI_PROFILE_PREFERENCE_LENGTH,
    MAX_AI_PROFILE_PREFERENCES,
)
from app.schemas.user_nutrition_profile import UserNutritionProfileRead
from app.services.ai_recipe_context import AIRecipeContextBuilder


class AIRecipeGenerationService:
    def __init__(
        self,
        db: AsyncSession,
        provider: RecipeGenerationProvider,
    ) -> None:
        self.pantry_repository = PantryRepository(db)
        self.nutrition_profiles_repository = UserNutritionProfilesRepository(db)
        self.provider = provider
        self.context_builder = AIRecipeContextBuilder()

    async def generate_preview(
        self,
        *,
        user_id: uuid.UUID,
        data: AIRecipeGenerationRequest,
    ) -> GeneratedRecipeData:
        pantry_items = await self.pantry_repository.list_user_pantry(user_id)
        nutrition_profile = await self.nutrition_profiles_repository.get_by_user_id(
            user_id
        )
        profile_read = (
            UserNutritionProfileRead.default()
            if nutrition_profile is None
            else UserNutritionProfileRead.model_validate(nutrition_profile)
        )
        self._validate_profile_context_limits(profile_read)
        context = self.context_builder.build_context(
            request=data,
            pantry_items=pantry_items,
            nutrition_profile=profile_read,
        )

        if data.use_only_pantry and not context.pantry_items:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Pantry is empty; use_only_pantry cannot be true",
            )

        provider_request = self.context_builder.build_provider_request(
            context=context,
        )

        try:
            generated_recipe = await self.provider.generate_recipe(
                provider_request=provider_request,
            )
            self._validate_generated_recipe(
                generated_recipe=generated_recipe,
                request=data,
                profile=profile_read,
                pantry_items=context.pantry_items,
            )
        except RecipeGenerationTimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI recipe generation timed out",
            ) from exc
        except RecipeGenerationUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI recipe generation is temporarily unavailable",
            ) from exc
        except RecipeGenerationInvalidResponseError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI provider returned an invalid recipe",
            ) from exc

        return generated_recipe

    def _validate_profile_context_limits(
        self,
        profile: UserNutritionProfileRead,
    ) -> None:
        preference_lists = (
            profile.allergies,
            profile.disliked_ingredients,
        )

        if any(
            len(values) > MAX_AI_PROFILE_PREFERENCES
            or any(len(value) > MAX_AI_PROFILE_PREFERENCE_LENGTH for value in values)
            for values in preference_lists
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=("Nutrition profile preferences exceed AI generation limits"),
            )

    def _validate_generated_recipe(
        self,
        *,
        generated_recipe: GeneratedRecipeData,
        request: AIRecipeGenerationRequest,
        profile: UserNutritionProfileRead,
        pantry_items: list[AIRecipePantryItemContext],
    ) -> None:
        if generated_recipe.servings != request.servings:
            raise RecipeGenerationInvalidResponseError

        if (
            request.max_prep_time_minutes is not None
            and generated_recipe.prep_time_minutes > request.max_prep_time_minutes
        ):
            raise RecipeGenerationInvalidResponseError

        for ingredient in generated_recipe.ingredients:
            if self._matches_any_restricted_name(
                ingredient.name,
                profile.allergies,
            ):
                raise RecipeGenerationInvalidResponseError

        if not request.use_only_pantry:
            return

        pantry_by_name = {
            self._normalize_name(item.name): item for item in pantry_items
        }

        for ingredient in generated_recipe.ingredients:
            pantry_item = pantry_by_name.get(self._normalize_name(ingredient.name))

            if pantry_item is None or ingredient.unit.casefold() != "g":
                raise RecipeGenerationInvalidResponseError

            quantity = Decimal(ingredient.quantity)

            if quantity > pantry_item.available_quantity_g:
                raise RecipeGenerationInvalidResponseError

    def _matches_any_restricted_name(
        self,
        ingredient_name: str,
        restricted_names: list[str],
    ) -> bool:
        normalized_ingredient = self._normalize_name(ingredient_name)
        padded_ingredient = f" {normalized_ingredient} "

        for restricted_name in restricted_names:
            normalized_restricted = self._normalize_name(restricted_name)

            if normalized_restricted and (
                f" {normalized_restricted} " in padded_ingredient
            ):
                return True

        return False

    def _normalize_name(self, value: str) -> str:
        return re.sub(r"[^\w]+", " ", value.casefold()).strip()
