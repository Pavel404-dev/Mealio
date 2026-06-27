from dataclasses import dataclass
from decimal import Decimal

from app.models.recipe import Recipe
from app.models.user_nutrition_profile import UserNutritionProfile
from app.schemas.user_nutrition_profile import UserNutritionProfileRead

NutritionProfile = UserNutritionProfile | UserNutritionProfileRead


@dataclass(frozen=True)
class RecipeSuggestionSortData:
    diet_type_priority: int
    calories_distance_missing: int
    calories_distance: Decimal


class RecipeSuggestionPersonalization:
    def should_exclude_recipe(
        self,
        *,
        recipe: Recipe,
        nutrition_profile: NutritionProfile,
    ) -> bool:
        blocked_ingredient_names = self._build_normalized_set(
            nutrition_profile.allergies
        ) | self._build_normalized_set(nutrition_profile.disliked_ingredients)

        if not blocked_ingredient_names:
            return False

        return any(
            self._normalize_text(recipe_ingredient.ingredient.name)
            in blocked_ingredient_names
            for recipe_ingredient in recipe.recipe_ingredients
        )

    def build_sort_data(
        self,
        *,
        recipe: Recipe,
        nutrition_profile: NutritionProfile,
    ) -> RecipeSuggestionSortData:
        calories_distance_missing, calories_distance = self._get_calories_sort_data(
            recipe=recipe,
            nutrition_profile=nutrition_profile,
        )

        return RecipeSuggestionSortData(
            diet_type_priority=self._get_diet_type_priority(
                recipe=recipe,
                nutrition_profile=nutrition_profile,
            ),
            calories_distance_missing=calories_distance_missing,
            calories_distance=calories_distance,
        )

    def _get_diet_type_priority(
        self,
        *,
        recipe: Recipe,
        nutrition_profile: NutritionProfile,
    ) -> int:
        preferred_diet_type = self._normalize_optional_text(
            nutrition_profile.diet_type,
        )

        if preferred_diet_type is None or preferred_diet_type == "balanced":
            return 0

        recipe_diet_type = self._normalize_optional_text(recipe.diet_type)

        if recipe_diet_type == preferred_diet_type:
            return 0

        return 1

    def _get_calories_sort_data(
        self,
        *,
        recipe: Recipe,
        nutrition_profile: NutritionProfile,
    ) -> tuple[int, Decimal]:
        calories_per_meal = self._get_calories_per_meal(nutrition_profile)

        if calories_per_meal is None:
            return 0, Decimal("0")

        if recipe.total_calories is None:
            return 1, Decimal("0")

        return (
            0,
            abs(self._to_decimal(recipe.total_calories) - calories_per_meal),
        )

    def _get_calories_per_meal(
        self,
        nutrition_profile: NutritionProfile,
    ) -> Decimal | None:
        if nutrition_profile.daily_calories_target is None:
            return None

        if nutrition_profile.preferred_meals_per_day is None:
            return None

        if nutrition_profile.preferred_meals_per_day <= 0:
            return None

        return self._to_decimal(
            nutrition_profile.daily_calories_target
        ) / self._to_decimal(nutrition_profile.preferred_meals_per_day)

    def _build_normalized_set(self, values: list[str] | None) -> set[str]:
        if not values:
            return set()

        return {
            normalized_value
            for value in values
            if (normalized_value := self._normalize_text(value))
        }

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None

        normalized_value = self._normalize_text(value)

        if not normalized_value:
            return None

        return normalized_value

    def _normalize_text(self, value: str) -> str:
        return value.strip().casefold()

    def _to_decimal(self, value) -> Decimal:
        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))
