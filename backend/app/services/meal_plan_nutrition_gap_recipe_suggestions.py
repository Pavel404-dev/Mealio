import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recipe import Recipe
from app.repositories.recipes import RecipesRepository
from app.schemas.meal_plan import (
    MealPlanNutritionGapRecipeSuggestionsRead,
    MealPlanNutritionGapRecommendationRead,
    NutritionGapRecipeSuggestionNutritionRead,
    NutritionGapRecipeSuggestionRead,
    NutritionGapRecipeSuggestionRecommendationRead,
    NutritionGapRecommendationAction,
    NutritionGapRecommendationMacro,
    NutritionGapRecommendationPriority,
)
from app.services.meal_plan_nutrition_progress import (
    MealPlanNutritionProgressService,
)
from app.services.recipe_suggestion_personalization import (
    RecipeSuggestionPersonalization,
)
from app.services.user_nutrition_profiles import UserNutritionProfilesService

PRIORITY_SCORE_WEIGHTS: dict[NutritionGapRecommendationPriority, Decimal] = {
    "high": Decimal("3"),
    "medium": Decimal("2"),
    "low": Decimal("1"),
}
RECIPE_MACRO_FIELDS: dict[NutritionGapRecommendationMacro, str] = {
    "calories": "total_calories",
    "protein": "total_protein_g",
    "carbs": "total_carbs_g",
    "fat": "total_fat_g",
}
SCORE_SCALE = Decimal("100")
SCORE_QUANTUM = Decimal("0.01")


class NutritionGapRecipeSuggestionCalculator:
    def build_suggestion(
        self,
        *,
        recipe: Recipe,
        recommendations: list[MealPlanNutritionGapRecommendationRead],
    ) -> NutritionGapRecipeSuggestionRead | None:
        total_weight = sum(
            (
                PRIORITY_SCORE_WEIGHTS[recommendation.priority]
                for recommendation in recommendations
            ),
            Decimal("0"),
        )

        if total_weight == Decimal("0"):
            return None

        weighted_coverage = Decimal("0")
        matched_actions: list[NutritionGapRecommendationAction] = []

        for recommendation in recommendations:
            if recommendation.macro is None:
                continue

            if recommendation.average_adjustment is None:
                continue

            macro_value = self._to_decimal(
                getattr(recipe, RECIPE_MACRO_FIELDS[recommendation.macro]),
            )

            if macro_value <= Decimal("0"):
                continue

            matched_actions.append(recommendation.action)

            coverage = min(
                macro_value / recommendation.average_adjustment,
                Decimal("1"),
            )
            weighted_coverage += (
                coverage * PRIORITY_SCORE_WEIGHTS[recommendation.priority]
            )

        if not matched_actions:
            return None

        score = (weighted_coverage / total_weight * SCORE_SCALE).quantize(
            SCORE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

        return NutritionGapRecipeSuggestionRead(
            recipe_id=recipe.id,
            recipe_title=recipe.title,
            diet_type=recipe.diet_type,
            score=score,
            matched_actions=matched_actions,
            nutrition=NutritionGapRecipeSuggestionNutritionRead(
                calories=self._to_decimal(recipe.total_calories),
                protein_g=self._to_decimal(recipe.total_protein_g),
                carbs_g=self._to_decimal(recipe.total_carbs_g),
                fat_g=self._to_decimal(recipe.total_fat_g),
            ),
        )

    def _to_decimal(self, value) -> Decimal:
        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))


class MealPlanNutritionGapRecipeSuggestionsService:
    def __init__(self, db: AsyncSession) -> None:
        self.recipes_repository = RecipesRepository(db)
        self.nutrition_progress_service = MealPlanNutritionProgressService(db)
        self.nutrition_profiles_service = UserNutritionProfilesService(db)
        self.personalization = RecipeSuggestionPersonalization()
        self.suggestion_calculator = NutritionGapRecipeSuggestionCalculator()

    async def get_current_user_recipe_suggestions(
        self,
        *,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 10,
    ) -> MealPlanNutritionGapRecipeSuggestionsRead:
        gap_recommendations = await self.nutrition_progress_service.get_current_user_nutrition_gap_recommendations(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        recommendations_used = [
            recommendation
            for recommendation in gap_recommendations.recommendations
            if recommendation.direction == "increase"
            and recommendation.average_adjustment is not None
        ]
        unresolved_actions = [
            recommendation.action
            for recommendation in gap_recommendations.recommendations
            if recommendation.action == "set_missing_targets"
            or recommendation.direction == "decrease"
        ]

        response_recommendations = [
            NutritionGapRecipeSuggestionRecommendationRead(
                action=recommendation.action,
                priority=recommendation.priority,
                average_adjustment=recommendation.average_adjustment,
            )
            for recommendation in recommendations_used
        ]

        if not recommendations_used:
            return MealPlanNutritionGapRecipeSuggestionsRead(
                start_date=gap_recommendations.start_date,
                end_date=gap_recommendations.end_date,
                recommendations_used=response_recommendations,
                unresolved_actions=unresolved_actions,
                suggestions=[],
            )

        recipes = await self.recipes_repository.list_for_nutrition_gap_suggestions(
            created_by_user_id=user_id,
            start_date=gap_recommendations.start_date,
            end_date=gap_recommendations.end_date,
        )
        nutrition_profile = (
            await self.nutrition_profiles_service.get_current_user_profile(user_id)
        )
        suggestions: list[NutritionGapRecipeSuggestionRead] = []

        for recipe in recipes:
            if self.personalization.should_exclude_recipe(
                recipe=recipe,
                nutrition_profile=nutrition_profile,
            ):
                continue

            personalization_sort_data = self.personalization.build_sort_data(
                recipe=recipe,
                nutrition_profile=nutrition_profile,
            )

            if personalization_sort_data.diet_type_priority > 0:
                continue

            suggestion = self.suggestion_calculator.build_suggestion(
                recipe=recipe,
                recommendations=recommendations_used,
            )

            if suggestion is not None:
                suggestions.append(suggestion)

        suggestions.sort(
            key=lambda suggestion: (
                -suggestion.score,
                suggestion.recipe_title,
                str(suggestion.recipe_id),
            )
        )

        return MealPlanNutritionGapRecipeSuggestionsRead(
            start_date=gap_recommendations.start_date,
            end_date=gap_recommendations.end_date,
            recommendations_used=response_recommendations,
            unresolved_actions=unresolved_actions,
            suggestions=suggestions[:limit],
        )
