import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingredient import Ingredient, UserIngredient
from app.models.recipe import Recipe
from app.repositories.recipes import RecipesRepository
from app.repositories.user_nutrition_profiles import UserNutritionProfilesRepository
from app.schemas.recipe import (
    RecipeCreate,
    RecipeIngredientCreate,
    RecipeNutritionTotals,
    RecipePantrySuggestionMissingIngredientRead,
    RecipePantrySuggestionRead,
    RecipeUpdate,
)
from app.schemas.user_nutrition_profile import UserNutritionProfileRead
from app.services.recipe_nutrition import RecipeNutritionCalculator
from app.services.recipe_suggestion_personalization import (
    RecipeSuggestionPersonalization,
    RecipeSuggestionSortData,
)


class RecipesService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = RecipesRepository(db)
        self.user_nutrition_profiles_repository = UserNutritionProfilesRepository(db)
        self.nutrition_calculator = RecipeNutritionCalculator()
        self.suggestion_personalization = RecipeSuggestionPersonalization()

    async def list_user_recipes(
        self,
        *,
        user_id: uuid.UUID,
        search: str | None = None,
        diet_type: str | None = None,
        min_calories: Decimal | None = None,
        max_calories: Decimal | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        if (
            min_calories is not None
            and max_calories is not None
            and min_calories > max_calories
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="min_calories must be less than or equal to max_calories",
            )

        return await self.repository.list(
            search=search,
            diet_type=diet_type,
            min_calories=min_calories,
            max_calories=max_calories,
            created_by_user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def suggest_recipes_from_pantry(
        self,
        *,
        user_id: uuid.UUID,
        diet_type: str | None = None,
        min_match_percent: Decimal = Decimal("0"),
        max_missing_ingredients: int | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[RecipePantrySuggestionRead]:
        recipes = await self.repository.list_for_pantry_suggestions(
            created_by_user_id=user_id,
            diet_type=diet_type,
        )
        pantry_by_ingredient_id = (
            await self.repository.list_user_pantry_by_ingredient_id(
                user_id=user_id,
            )
        )
        nutrition_profile = (
            await self.user_nutrition_profiles_repository.get_by_user_id(
                user_id,
            )
        )

        if nutrition_profile is None:
            nutrition_profile = UserNutritionProfileRead.default()

        suggestions_with_sort_data: list[
            tuple[
                RecipePantrySuggestionRead,
                Decimal,
                RecipeSuggestionSortData,
            ]
        ] = []

        for recipe in recipes:
            if self.suggestion_personalization.should_exclude_recipe(
                recipe=recipe,
                nutrition_profile=nutrition_profile,
            ):
                continue

            suggestion = self._build_pantry_suggestion(
                recipe=recipe,
                pantry_by_ingredient_id=pantry_by_ingredient_id,
            )

            if suggestion is None:
                continue

            if suggestion.match_percent < min_match_percent:
                continue

            if (
                max_missing_ingredients is not None
                and suggestion.missing_ingredients_count > max_missing_ingredients
            ):
                continue

            total_missing_quantity_g = sum(
                (
                    missing_ingredient.missing_quantity_g
                    for missing_ingredient in suggestion.missing_ingredients
                ),
                Decimal("0"),
            )
            personalized_sort_data = self.suggestion_personalization.build_sort_data(
                recipe=recipe,
                nutrition_profile=nutrition_profile,
            )

            suggestions_with_sort_data.append(
                (
                    suggestion,
                    total_missing_quantity_g,
                    personalized_sort_data,
                )
            )

        suggestions_with_sort_data.sort(
            key=lambda item: (
                item[2].diet_type_priority,
                -item[0].match_percent,
                item[2].calories_distance_missing,
                item[2].calories_distance,
                item[0].missing_ingredients_count,
                item[1],
                item[0].recipe_title.lower(),
                str(item[0].recipe_id),
            )
        )

        paginated_suggestions = suggestions_with_sort_data[offset : offset + limit]

        return [suggestion for suggestion, _, _ in paginated_suggestions]

    async def get_recipe(
        self,
        *,
        user_id: uuid.UUID,
        recipe_id: uuid.UUID,
    ):
        recipe = await self.repository.get_by_id(
            recipe_id=recipe_id,
            created_by_user_id=user_id,
        )

        if recipe is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipe not found",
            )

        return recipe

    async def create_recipe(
        self,
        *,
        user_id: uuid.UUID,
        data: RecipeCreate,
    ):
        ingredients_by_id = await self._get_existing_ingredients_by_id(data.ingredients)
        self._validate_all_ingredients_exist(
            ingredients=data.ingredients,
            ingredients_by_id=ingredients_by_id,
        )

        nutrition_totals = self.nutrition_calculator.calculate_from_ingredient_inputs(
            ingredients=data.ingredients,
            ingredients_by_id=ingredients_by_id,
        )

        return await self.repository.create(
            created_by_user_id=user_id,
            data=data,
            nutrition_totals=nutrition_totals,
        )

    async def update_recipe(
        self,
        *,
        user_id: uuid.UUID,
        recipe_id: uuid.UUID,
        data: RecipeUpdate,
    ):
        recipe = await self.get_recipe(
            user_id=user_id,
            recipe_id=recipe_id,
        )

        nutrition_totals: RecipeNutritionTotals | None = None

        if data.ingredients is not None:
            ingredients_by_id = await self._get_existing_ingredients_by_id(
                data.ingredients
            )
            self._validate_all_ingredients_exist(
                ingredients=data.ingredients,
                ingredients_by_id=ingredients_by_id,
            )

            nutrition_totals = (
                self.nutrition_calculator.calculate_from_ingredient_inputs(
                    ingredients=data.ingredients,
                    ingredients_by_id=ingredients_by_id,
                )
            )

        return await self.repository.update(
            recipe=recipe,
            data=data,
            nutrition_totals=nutrition_totals,
        )

    async def delete_recipe(
        self,
        *,
        user_id: uuid.UUID,
        recipe_id: uuid.UUID,
    ) -> None:
        recipe = await self.get_recipe(
            user_id=user_id,
            recipe_id=recipe_id,
        )

        if await self.repository.is_used_in_meal_plan_items(recipe.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Recipe is used in meal plans and cannot be deleted",
            )
        await self.repository.delete(recipe.id)

    async def _get_existing_ingredients_by_id(
        self,
        ingredients: list[RecipeIngredientCreate],
    ) -> dict[uuid.UUID, Ingredient]:
        ingredient_ids = [item.ingredient_id for item in ingredients]

        if not ingredient_ids:
            return {}

        existing_ingredients = await self.repository.get_ingredients_by_ids(
            ingredient_ids
        )

        return {ingredient.id: ingredient for ingredient in existing_ingredients}

    def _validate_all_ingredients_exist(
        self,
        *,
        ingredients: list[RecipeIngredientCreate],
        ingredients_by_id: dict[uuid.UUID, Ingredient],
    ) -> None:
        missing_ids = [
            str(item.ingredient_id)
            for item in ingredients
            if item.ingredient_id not in ingredients_by_id
        ]

        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ingredients not found: {', '.join(missing_ids)}",
            )

    def _build_pantry_suggestion(
        self,
        *,
        recipe: Recipe,
        pantry_by_ingredient_id: dict[uuid.UUID, UserIngredient],
    ) -> RecipePantrySuggestionRead | None:
        recipe_ingredients = recipe.recipe_ingredients
        total_ingredients_count = len(recipe_ingredients)

        if total_ingredients_count == 0:
            return None

        matched_ingredients_count = 0
        missing_ingredients: list[RecipePantrySuggestionMissingIngredientRead] = []

        for recipe_ingredient in recipe_ingredients:
            required_quantity_g = self._to_decimal(recipe_ingredient.quantity_g)
            pantry_item = pantry_by_ingredient_id.get(recipe_ingredient.ingredient_id)
            pantry_quantity_g = (
                self._to_decimal(pantry_item.quantity_g)
                if pantry_item is not None
                else Decimal("0")
            )
            missing_quantity_g = max(
                required_quantity_g - pantry_quantity_g,
                Decimal("0"),
            )

            if missing_quantity_g == Decimal("0"):
                matched_ingredients_count += 1
                continue

            missing_ingredients.append(
                RecipePantrySuggestionMissingIngredientRead(
                    ingredient_id=recipe_ingredient.ingredient_id,
                    ingredient_name=recipe_ingredient.ingredient.name,
                    required_quantity_g=required_quantity_g,
                    pantry_quantity_g=pantry_quantity_g,
                    missing_quantity_g=missing_quantity_g,
                )
            )

        match_percent = (
            Decimal(matched_ingredients_count)
            / Decimal(total_ingredients_count)
            * Decimal("100")
        ).quantize(Decimal("0.01"))

        return RecipePantrySuggestionRead(
            recipe_id=recipe.id,
            recipe_title=recipe.title,
            diet_type=recipe.diet_type,
            total_calories=recipe.total_calories,
            match_percent=match_percent,
            matched_ingredients_count=matched_ingredients_count,
            missing_ingredients_count=len(missing_ingredients),
            total_ingredients_count=total_ingredients_count,
            missing_ingredients=missing_ingredients,
        )

    def _to_decimal(self, value) -> Decimal:
        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))
