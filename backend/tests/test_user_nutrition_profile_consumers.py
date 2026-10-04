from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.schemas.user_nutrition_profile import UserNutritionProfileRead
from app.services.meal_plan_nutrition_progress import (
    MealPlanNutritionProgressCalculator,
)
from app.services.recipe_suggestion_personalization import (
    RecipeSuggestionPersonalization,
)


def test_onboarding_values_preserve_explicit_nutrition_calculations():
    old_profile = UserNutritionProfileRead(
        daily_calories_target=2400,
        daily_protein_target_g=150,
        daily_carbs_target_g=300,
        daily_fat_target_g=80,
    )
    extended = old_profile.model_copy(
        update={
            "sex": "female",
            "birth_date": date(1990, 1, 2),
            "height_cm": Decimal("170.5"),
            "weight_kg": Decimal("70.25"),
            "activity_level": "extra_active",
            "max_cooking_time_minutes": 1,
            "weekly_food_budget_amount": Decimal("0.01"),
            "budget_currency": "EUR",
        }
    )
    row = {
        "date": date(2026, 10, 4),
        "total_calories": Decimal("2200"),
        "total_protein_g": Decimal("140"),
        "total_carbs_g": Decimal("280"),
        "total_fat_g": Decimal("75"),
    }
    calculator = MealPlanNutritionProgressCalculator()
    before = calculator.build_day_progress(row=row, profile=old_profile)
    after = calculator.build_day_progress(row=row, profile=extended)
    assert before == after
    assert after.remaining_calories == Decimal("200")
    assert after.remaining_protein_g == Decimal("10")
    assert calculator.build_day_gaps(
        row=row, profile=old_profile
    ) == calculator.build_day_gaps(row=row, profile=extended)


def test_onboarding_values_preserve_pantry_personalization_and_restrictions():
    old_profile = UserNutritionProfileRead(
        daily_calories_target=2400,
        preferred_meals_per_day=3,
        diet_type="vegan",
        allergies=["peanuts"],
        disliked_ingredients=["celery"],
    )
    extended = old_profile.model_copy(
        update={
            "height_cm": Decimal("170.0"),
            "weight_kg": Decimal("70.25"),
            "activity_level": "extra_active",
            "max_cooking_time_minutes": 1,
            "weekly_food_budget_amount": Decimal("0.01"),
            "budget_currency": "EUR",
        }
    )
    personalization = RecipeSuggestionPersonalization()
    for name, excluded in [("Peanuts", True), (" CELERY ", True), ("Rice", False)]:
        recipe = SimpleNamespace(
            total_calories=Decimal("700"),
            diet_type="vegan",
            prep_time_minutes=60,
            recipe_ingredients=[SimpleNamespace(ingredient=SimpleNamespace(name=name))],
        )
        assert (
            personalization.should_exclude_recipe(
                recipe=recipe, nutrition_profile=old_profile
            )
            == excluded
        )
        assert (
            personalization.should_exclude_recipe(
                recipe=recipe, nutrition_profile=extended
            )
            == excluded
        )
        old_sort = personalization.build_sort_data(
            recipe=recipe, nutrition_profile=old_profile
        )
        assert (
            personalization.build_sort_data(recipe=recipe, nutrition_profile=extended)
            == old_sort
        )
        assert old_sort.calories_distance == Decimal("100")
