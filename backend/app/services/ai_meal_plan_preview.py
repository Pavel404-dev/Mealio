import json
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from time import monotonic
from typing import get_args

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.meal_plan_generation import (
    MealPlanGenerationProvider,
    MealPlanProviderInvalidOutput,
    MealPlanProviderTimeout,
    MealPlanProviderUnavailable,
)
from app.models.recipe import Recipe
from app.repositories.recipes import RecipesRepository
from app.repositories.user_nutrition_profiles import UserNutritionProfilesRepository
from app.schemas.ai_meal_plan import (
    AIMealPlanPreview,
    AIMealPlanPreviewItem,
    AIMealPlanPreviewRequest,
    GeneratedMealPlanSelection,
    MAX_PLAN_CANDIDATES,
)
from app.schemas.meal_plan_v2 import MealSlot
from app.schemas.recipe import RecipeNutritionTotals
from app.schemas.user_nutrition_profile import UserNutritionProfileRead
from app.services.gram_nutrition import NUTRIENTS, TOTALS, round_nutrition_hundredths
from app.services.recipe_suggestion_personalization import (
    RecipeSuggestionPersonalization,
)

logger = logging.getLogger("uvicorn.error.mealio.ai_meal_plan")
CANONICAL_SLOTS = get_args(MealSlot)


@dataclass(frozen=True)
class Candidate:
    recipe_id: uuid.UUID
    servings: int
    allowed_slots: tuple[MealSlot, ...]
    nutrition: dict[str, Decimal]
    diet_type: str | None
    liked_ingredients: int

    def provider_context(self, number: int) -> dict:
        return {
            "candidate_number": number,
            "allowed_slots": self.allowed_slots,
            "recipe_servings": self.servings,
            "whole_recipe_nutrition": self.nutrition,
            "diet_type": self.diet_type,
            "liked_ingredient_count": self.liked_ingredients,
        }


class AIMealPlanPreviewService:
    def __init__(self, db: AsyncSession, provider: MealPlanGenerationProvider) -> None:
        self.db = db
        self.provider = provider
        self.recipes = RecipesRepository(db)
        self.profiles = UserNutritionProfilesRepository(db)
        self.personalization = RecipeSuggestionPersonalization()

    async def generate(
        self, *, user_id: uuid.UUID, request: AIMealPlanPreviewRequest
    ) -> AIMealPlanPreview:
        stored_profile = await self.profiles.get_by_user_id(user_id)
        profile = (
            UserNutritionProfileRead.model_validate(stored_profile)
            if stored_profile is not None
            else UserNutritionProfileRead.default()
        )
        if any(value.strip() for value in profile.allergies):
            raise HTTPException(
                422, "AI meal plans do not support declared allergies yet"
            )

        recipes = await self.recipes.list_for_plan_preview(
            user_id=user_id, limit=MAX_PLAN_CANDIDATES
        )
        candidates = self._build_candidates(recipes, profile, request.meal_types)
        allowed_slots = {
            slot
            for candidate in candidates.values()
            for slot in candidate.allowed_slots
        }
        if not set(request.meal_types) <= allowed_slots:
            raise HTTPException(
                422, "Not enough eligible saved recipes for the requested meal slots"
            )

        # Release this read-only transaction before an external network call.
        await self.db.rollback()
        context_json = json.dumps(
            {
                **request.model_dump(mode="json"),
                "preferences": {
                    "goal": profile.goal,
                    "diet_type": profile.diet_type,
                    "preferred_meals_per_day": profile.preferred_meals_per_day,
                    "allergies": [],
                    "daily_targets": {
                        "calories": profile.daily_calories_target,
                        "protein_g": profile.daily_protein_target_g,
                        "carbs_g": profile.daily_carbs_target_g,
                        "fat_g": profile.daily_fat_target_g,
                    },
                },
                "candidates": [c.provider_context(n) for n, c in candidates.items()],
            },
            default=str,
            ensure_ascii=False,
        )
        started = monotonic()
        usage = None
        outcome = "error"
        try:
            usage = await self.provider.select_meals(context_json=context_json)
            selection = GeneratedMealPlanSelection.model_validate(usage.selection)
            preview = self._build_preview(request, selection, candidates)
            outcome = "success"
            return preview
        except (ValidationError, MealPlanProviderInvalidOutput) as exc:
            outcome = "invalid_output"
            raise HTTPException(
                502, "AI provider returned an invalid meal plan"
            ) from exc
        except MealPlanProviderTimeout as exc:
            outcome = "timeout"
            raise HTTPException(503, "AI meal plan preview timed out") from exc
        except MealPlanProviderUnavailable as exc:
            outcome = "unavailable"
            raise HTTPException(
                503, "AI meal plan preview is temporarily unavailable"
            ) from exc
        finally:
            logger.info(
                "ai_meal_plan_preview model=%r outcome=%s latency_ms=%d input_tokens=%s output_tokens=%s cost_usd=unknown",
                self.provider.model,
                outcome,
                round((monotonic() - started) * 1000),
                usage.input_tokens if usage else None,
                usage.output_tokens if usage else None,
            )

    def _build_candidates(
        self,
        recipes: list[Recipe],
        profile: UserNutritionProfileRead,
        slots: list[MealSlot],
    ) -> dict[int, Candidate]:
        candidates = {}
        liked = {name.strip().casefold() for name in profile.liked_ingredients}
        for recipe in recipes:
            if not _recipe_has_complete_nutrition(recipe):
                continue
            if self.personalization.should_exclude_recipe(
                recipe=recipe, nutrition_profile=profile
            ):
                continue
            allowed = tuple(
                slot
                for slot in slots
                if recipe.meal_type not in CANONICAL_SLOTS or slot == recipe.meal_type
            )
            if not allowed:
                continue
            candidates[len(candidates) + 1] = Candidate(
                recipe_id=recipe.id,
                servings=recipe.servings,
                allowed_slots=allowed,
                nutrition={field: getattr(recipe, field) for field in TOTALS},
                diet_type=recipe.diet_type,
                liked_ingredients=sum(
                    row.ingredient.name.strip().casefold() in liked
                    for row in recipe.recipe_ingredients
                ),
            )
        return candidates

    def _build_preview(
        self,
        request: AIMealPlanPreviewRequest,
        selection: GeneratedMealPlanSelection,
        candidates: dict[int, Candidate],
    ) -> AIMealPlanPreview:
        by_slot = {item.meal_type: item for item in selection.items}
        if len(selection.items) != len(by_slot) or set(by_slot) != set(
            request.meal_types
        ):
            raise MealPlanProviderInvalidOutput

        totals = dict.fromkeys(TOTALS, Fraction(0))
        assignments = []
        for slot in request.meal_types:
            item = by_slot[slot]
            candidate = candidates.get(item.candidate_number)
            if candidate is None or slot not in candidate.allowed_slots:
                raise MealPlanProviderInvalidOutput
            multiplier = Fraction(item.serving_hundredths, 100 * candidate.servings)
            for field, amount in candidate.nutrition.items():
                totals[field] += Fraction(amount) * multiplier
            assignments.append(
                AIMealPlanPreviewItem(
                    recipe_id=candidate.recipe_id,
                    planned_date=request.planned_date,
                    meal_type=slot,
                    planned_servings=Decimal(f"{item.serving_hundredths}e-2"),
                )
            )
        return AIMealPlanPreview(
            items=assignments,
            nutrition=RecipeNutritionTotals(
                **{
                    field: round_nutrition_hundredths(total)
                    for field, total in totals.items()
                }
            ),
        )


def _recipe_has_complete_nutrition(recipe: Recipe) -> bool:
    def nonnegative(value: Decimal | None) -> bool:
        return value is not None and value.is_finite() and value >= 0

    if not recipe.recipe_ingredients or not 1 <= recipe.servings <= 12:
        return False
    if not all(nonnegative(getattr(recipe, field)) for field in TOTALS):
        return False
    for row in recipe.recipe_ingredients:
        if row.ingredient is None:
            return False
        value = row.ingredient.nutrition_value
        if (
            not nonnegative(row.quantity_g)
            or row.quantity_g == 0
            or value is None
            or not nonnegative(value.portion_g)
            or value.portion_g == 0
            or not all(nonnegative(getattr(value, field)) for field in NUTRIENTS)
        ):
            return False
    return True
