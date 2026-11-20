import json
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from itertools import product
from math import lcm
from time import monotonic
from typing import get_args

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

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
    AIMealPlanTargetFit,
    AIMealPlanTargetFitMetric,
    AIMealPlanTargetFitMetrics,
    GeneratedMealPlanSelection,
    GeneratedMealSlot,
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
TRIAL_SERVING_HUNDREDTHS = (75, 100, 125, 150)


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

    def nutrition_for(self, serving_hundredths: int) -> dict[str, Fraction]:
        multiplier = Fraction(serving_hundredths, 100 * self.servings)
        return {
            field: Fraction(total) * multiplier
            for field, total in self.nutrition.items()
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
        daily_targets = {
            "total_calories": profile.daily_calories_target,
            "total_protein_g": profile.daily_protein_target_g,
            "total_carbs_g": profile.daily_carbs_target_g,
            "total_fat_g": profile.daily_fat_target_g,
        }
        context_json = json.dumps(
            {
                **request.model_dump(mode="json"),
                "preferences": {
                    "goal": profile.goal,
                    "diet_type": profile.diet_type,
                    "preferred_meals_per_day": profile.preferred_meals_per_day,
                    "allergies": [],
                    "daily_targets": {
                        field.removeprefix("total_"): value
                        for field, value in daily_targets.items()
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
            preview = await self._build_preview(
                request, selection, candidates, profile, daily_targets
            )
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
            estimated_cost = usage.estimated_cost_usd if usage else None
            logger.info(
                "ai_meal_plan_preview model=%r outcome=%s latency_ms=%d "
                "input_tokens=%s output_tokens=%s cost_usd=%s",
                self.provider.model,
                outcome,
                round((monotonic() - started) * 1000),
                usage.input_tokens if usage else None,
                usage.output_tokens if usage else None,
                format(estimated_cost, "f")
                if estimated_cost is not None
                else "unknown",
            )

    def _build_candidates(
        self,
        recipes: list[Recipe],
        profile: UserNutritionProfileRead,
        slots: list[MealSlot],
    ) -> dict[int, Candidate]:
        candidates = {}
        preferred_diet = (profile.diet_type or "").strip().casefold()
        liked = {name.strip().casefold() for name in profile.liked_ingredients}
        for recipe in recipes:
            if (
                preferred_diet not in ("", "balanced")
                and (recipe.diet_type or "").strip().casefold() != preferred_diet
            ):
                continue
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

    async def _build_preview(
        self,
        request: AIMealPlanPreviewRequest,
        selection: GeneratedMealPlanSelection,
        candidates: dict[int, Candidate],
        profile: UserNutritionProfileRead,
        daily_targets: dict[str, int | None],
    ) -> AIMealPlanPreview:
        by_slot = {item.meal_type: item for item in selection.items}
        if len(selection.items) != len(by_slot) or set(by_slot) != set(
            request.meal_types
        ):
            raise MealPlanProviderInvalidOutput

        items = [by_slot[slot] for slot in request.meal_types]
        for item in items:
            candidate = candidates.get(item.candidate_number)
            if candidate is None or item.meal_type not in candidate.allowed_slots:
                raise MealPlanProviderInvalidOutput

        targets = {
            field: value for field, value in daily_targets.items() if value is not None
        }
        if targets and len(items) == profile.preferred_meals_per_day:
            items = await run_in_threadpool(
                _fit_daily_targets, items, candidates, targets
            )

        totals = dict.fromkeys(TOTALS, Fraction(0))
        assignments = []
        for item in items:
            candidate = candidates[item.candidate_number]
            for field, amount in candidate.nutrition_for(
                item.serving_hundredths
            ).items():
                totals[field] += amount
            assignments.append(
                AIMealPlanPreviewItem(
                    recipe_id=candidate.recipe_id,
                    planned_date=request.planned_date,
                    meal_type=item.meal_type,
                    planned_servings=Decimal(f"{item.serving_hundredths}e-2"),
                )
            )
        nutrition = RecipeNutritionTotals(
            **{
                field: round_nutrition_hundredths(total)
                for field, total in totals.items()
            }
        )
        return AIMealPlanPreview(
            items=assignments,
            nutrition=nutrition,
            target_fit=_build_target_fit(
                nutrition, daily_targets, len(items), profile.preferred_meals_per_day
            ),
        )


def _build_target_fit(
    nutrition: RecipeNutritionTotals,
    daily_targets: dict[str, int | None],
    requested_meals: int,
    preferred_meals: int | None,
) -> AIMealPlanTargetFit:
    reason = None
    if not any(target is not None for target in daily_targets.values()):
        reason = "no_targets"
    elif preferred_meals is None:
        reason = "unknown_meal_count"
    elif requested_meals != preferred_meals:
        reason = "partial_day"

    metrics = {}
    for field in TOTALS:
        target = daily_targets[field]
        actual = getattr(nutrition, field)
        delta = Fraction(actual) - target if target is not None else None
        percent = delta * 100 / target if target is not None else None
        metrics[field] = AIMealPlanTargetFitMetric(
            target=target,
            actual=actual,
            delta=round_nutrition_hundredths(delta) if delta is not None else None,
            delta_percent=round_nutrition_hundredths(percent)
            if percent is not None
            else None,
            within_tolerance=abs(percent) <= 10
            if reason is None and percent is not None
            else None,
        )

    status = "not_evaluated"
    if reason is None:
        status = (
            "outside_tolerance"
            if any(metric.within_tolerance is False for metric in metrics.values())
            else "within_tolerance"
        )
    return AIMealPlanTargetFit(
        status=status,
        reason=reason,
        metrics=AIMealPlanTargetFitMetrics(**metrics),
    )


@dataclass(frozen=True)
class _PortionOption:
    item: GeneratedMealSlot
    relative_nutrition_units: tuple[int, ...]


def _fit_daily_targets(
    items: list[GeneratedMealSlot],
    candidates: dict[int, Candidate],
    targets: dict[str, int],
) -> list[GeneratedMealSlot]:
    relative_per_hundredth = {}
    for number, candidate in candidates.items():
        nutrition = candidate.nutrition_for(1)
        relative_per_hundredth[number] = tuple(
            nutrition[field] / target for field, target in targets.items()
        )

    # A common denominator keeps scoring exact with integer sums.
    target_units = lcm(
        *(
            amount.denominator
            for nutrition in relative_per_hundredth.values()
            for amount in nutrition
        )
    )
    units_per_hundredth = {
        number: tuple(
            amount.numerator * (target_units // amount.denominator)
            for amount in nutrition
        )
        for number, nutrition in relative_per_hundredth.items()
    }
    options_by_slot = [
        [
            _PortionOption(
                item=option,
                relative_nutrition_units=tuple(
                    units * option.serving_hundredths
                    for units in units_per_hundredth[option.candidate_number]
                ),
            )
            for option in _portion_options(item, candidates)
        ]
        for item in items
    ]

    def score(plan: tuple[_PortionOption, ...]) -> tuple[int, int, int]:
        deviations = [
            abs(sum(values) - target_units)
            for values in zip(
                *(option.relative_nutrition_units for option in plan), strict=True
            )
        ]
        liked = sum(
            candidates[option.item.candidate_number].liked_ingredients
            for option in plan
        )
        return max(deviations), sum(deviations), -liked

    best = min(product(*options_by_slot), key=score)
    return [option.item for option in best]


def _portion_options(
    item: GeneratedMealSlot, candidates: dict[int, Candidate]
) -> list[GeneratedMealSlot]:
    alternatives = (
        number
        for number, candidate in candidates.items()
        if number != item.candidate_number and item.meal_type in candidate.allowed_slots
    )
    # Try one alternative per slot, preferring liked ingredients and then recency.
    alternative = max(
        alternatives,
        key=lambda number: candidates[number].liked_ingredients,
        default=None,
    )
    # First in the search so the original plan wins a complete tie.
    options = [item]
    for number in (item.candidate_number, alternative):
        if number is None:
            continue
        for serving_hundredths in TRIAL_SERVING_HUNDREDTHS:
            if (number, serving_hundredths) == (
                item.candidate_number,
                item.serving_hundredths,
            ):
                continue
            options.append(
                GeneratedMealSlot(
                    meal_type=item.meal_type,
                    candidate_number=number,
                    serving_hundredths=serving_hundredths,
                )
            )
    return options


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
