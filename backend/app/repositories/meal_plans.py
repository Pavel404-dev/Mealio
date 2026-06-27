import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ingredient import Ingredient, UserIngredient
from app.models.meal_plan import MealPlan, MealPlanItem
from app.models.recipe import Recipe, RecipeIngredient
from app.models.user import User
from app.schemas.meal_plan import (
    MealPlanCreate,
    MealPlanItemCreate,
    MealPlanItemUpdate,
    MealPlanUpdate,
)


class MealPlanItemSlotConflictError(Exception):
    pass


def normalize_meal_type(meal_type: str) -> str:
    return meal_type.strip().lower()


class MealPlansRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))

        return result.scalar_one_or_none()

    async def get_recipe(
        self,
        *,
        user_id: uuid.UUID,
        recipe_id: uuid.UUID,
    ) -> Recipe | None:
        result = await self.db.execute(
            select(Recipe).where(
                Recipe.id == recipe_id,
                Recipe.created_by_user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_recipes_by_ids(
        self,
        *,
        user_id: uuid.UUID,
        recipe_ids: list[uuid.UUID],
    ) -> list[Recipe]:
        if not recipe_ids:
            return []

        stmt = select(Recipe).where(
            Recipe.id.in_(recipe_ids),
            Recipe.created_by_user_id == user_id,
        )
        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        search: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MealPlan]:
        stmt = (
            select(MealPlan)
            .options(selectinload(MealPlan.items))
            .where(MealPlan.user_id == user_id)
        )

        if search:
            search_term = search.strip()

            if search_term:
                stmt = stmt.where(MealPlan.title.ilike(f"%{search_term}%"))

        if from_date is not None:
            stmt = stmt.where(
                or_(
                    MealPlan.end_date.is_(None),
                    MealPlan.end_date >= from_date,
                )
            )

        if to_date is not None:
            stmt = stmt.where(MealPlan.start_date <= to_date)

        stmt = (
            stmt.order_by(MealPlan.start_date.desc(), MealPlan.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    async def list_items_for_user_calendar(
        self,
        *,
        user_id: uuid.UUID,
        from_date: date,
        to_date: date,
        meal_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        stmt = (
            select(
                MealPlanItem.id.label("id"),
                MealPlanItem.meal_plan_id.label("meal_plan_id"),
                MealPlan.title.label("meal_plan_title"),
                MealPlanItem.recipe_id.label("recipe_id"),
                Recipe.title.label("recipe_title"),
                MealPlanItem.planned_date.label("planned_date"),
                MealPlanItem.meal_type.label("meal_type"),
            )
            .select_from(MealPlanItem)
            .join(MealPlan, MealPlan.id == MealPlanItem.meal_plan_id)
            .join(Recipe, Recipe.id == MealPlanItem.recipe_id)
            .where(
                MealPlan.user_id == user_id,
                MealPlanItem.planned_date >= from_date,
                MealPlanItem.planned_date <= to_date,
            )
        )

        if meal_type is not None:
            stmt = stmt.where(
                func.lower(MealPlanItem.meal_type) == normalize_meal_type(meal_type)
            )

        stmt = (
            stmt.order_by(
                MealPlanItem.planned_date.asc(),
                MealPlanItem.meal_type.asc(),
                MealPlanItem.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)

        return [dict(row._mapping) for row in result.all()]

    async def list_nutrition_progress_for_user_calendar(
        self,
        *,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        total_calories = func.coalesce(
            func.sum(func.coalesce(Recipe.total_calories, Decimal("0"))),
            Decimal("0"),
        ).label("total_calories")
        total_protein_g = func.coalesce(
            func.sum(func.coalesce(Recipe.total_protein_g, Decimal("0"))),
            Decimal("0"),
        ).label("total_protein_g")
        total_carbs_g = func.coalesce(
            func.sum(func.coalesce(Recipe.total_carbs_g, Decimal("0"))),
            Decimal("0"),
        ).label("total_carbs_g")
        total_fat_g = func.coalesce(
            func.sum(func.coalesce(Recipe.total_fat_g, Decimal("0"))),
            Decimal("0"),
        ).label("total_fat_g")

        stmt = (
            select(
                MealPlanItem.planned_date.label("date"),
                total_calories,
                total_protein_g,
                total_carbs_g,
                total_fat_g,
            )
            .select_from(MealPlanItem)
            .join(MealPlan, MealPlan.id == MealPlanItem.meal_plan_id)
            .join(Recipe, Recipe.id == MealPlanItem.recipe_id)
            .where(
                MealPlan.user_id == user_id,
                Recipe.created_by_user_id == user_id,
            )
        )

        if start_date is not None:
            stmt = stmt.where(MealPlanItem.planned_date >= start_date)

        if end_date is not None:
            stmt = stmt.where(MealPlanItem.planned_date <= end_date)

        stmt = stmt.group_by(MealPlanItem.planned_date).order_by(
            MealPlanItem.planned_date.asc(),
        )

        result = await self.db.execute(stmt)

        return [dict(row._mapping) for row in result.all()]

    async def list_shopping_list_for_meal_plan(
        self,
        *,
        user_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
        meal_type: str | None = None,
        subtract_pantry: bool = False,
    ) -> list[dict]:
        required_quantity = func.coalesce(
            func.sum(RecipeIngredient.quantity_g),
            Decimal("0"),
        ).label("required_quantity_g")

        required_stmt = (
            select(
                RecipeIngredient.ingredient_id.label("ingredient_id"),
                required_quantity,
            )
            .select_from(MealPlanItem)
            .join(MealPlan, MealPlan.id == MealPlanItem.meal_plan_id)
            .join(Recipe, Recipe.id == MealPlanItem.recipe_id)
            .join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
            .where(
                MealPlan.id == meal_plan_id,
                MealPlan.user_id == user_id,
            )
        )

        if from_date is not None:
            required_stmt = required_stmt.where(MealPlanItem.planned_date >= from_date)

        if to_date is not None:
            required_stmt = required_stmt.where(MealPlanItem.planned_date <= to_date)

        if meal_type is not None:
            required_stmt = required_stmt.where(
                func.lower(MealPlanItem.meal_type) == normalize_meal_type(meal_type)
            )

        required_subquery = required_stmt.group_by(
            RecipeIngredient.ingredient_id,
        ).subquery()

        selected_columns = [
            Ingredient.id.label("ingredient_id"),
            Ingredient.name.label("ingredient_name"),
            Ingredient.category.label("ingredient_category"),
            required_subquery.c.required_quantity_g.label("required_quantity_g"),
        ]

        stmt = (
            select(*selected_columns)
            .select_from(required_subquery)
            .join(Ingredient, Ingredient.id == required_subquery.c.ingredient_id)
        )

        if subtract_pantry:
            pantry_quantity = func.coalesce(
                UserIngredient.quantity_g,
                Decimal("0"),
            )
            missing_quantity = case(
                (
                    required_subquery.c.required_quantity_g > pantry_quantity,
                    required_subquery.c.required_quantity_g - pantry_quantity,
                ),
                else_=Decimal("0"),
            )

            stmt = stmt.add_columns(
                pantry_quantity.label("pantry_quantity_g"),
                missing_quantity.label("missing_quantity_g"),
            ).outerjoin(
                UserIngredient,
                and_(
                    UserIngredient.user_id == user_id,
                    UserIngredient.ingredient_id == Ingredient.id,
                ),
            )

        stmt = stmt.order_by(
            Ingredient.name.asc(),
            Ingredient.id.asc(),
        )

        result = await self.db.execute(stmt)

        return [dict(row._mapping) for row in result.all()]

    async def get_by_id(
        self,
        *,
        user_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
    ) -> MealPlan | None:
        stmt = (
            select(MealPlan)
            .options(selectinload(MealPlan.items))
            .where(
                MealPlan.id == meal_plan_id,
                MealPlan.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        data: MealPlanCreate,
    ) -> MealPlan:
        meal_plan = MealPlan(
            user_id=user_id,
            title=data.title.strip(),
            start_date=data.start_date,
            end_date=data.end_date,
        )

        meal_plan.items = [
            MealPlanItem(
                recipe_id=item.recipe_id,
                planned_date=item.planned_date,
                meal_type=normalize_meal_type(item.meal_type),
            )
            for item in data.items
        ]

        self.db.add(meal_plan)

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise MealPlanItemSlotConflictError from exc

        created = await self.get_by_id(
            user_id=user_id,
            meal_plan_id=meal_plan.id,
        )

        if created is None:
            raise RuntimeError("Created meal plan was not found")

        return created

    async def update(
        self,
        *,
        meal_plan: MealPlan,
        data: MealPlanUpdate,
    ) -> MealPlan:
        update_data = data.model_dump(exclude_unset=True)

        if "title" in update_data and data.title is not None:
            meal_plan.title = data.title.strip()

        if "start_date" in update_data and data.start_date is not None:
            meal_plan.start_date = data.start_date

        if "end_date" in update_data:
            meal_plan.end_date = data.end_date

        await self.db.commit()

        updated = await self.get_by_id(
            user_id=meal_plan.user_id,
            meal_plan_id=meal_plan.id,
        )

        if updated is None:
            raise RuntimeError("Updated meal plan was not found")

        return updated

    async def delete(self, meal_plan_id: uuid.UUID) -> None:
        stmt = delete(MealPlan).where(MealPlan.id == meal_plan_id)

        await self.db.execute(stmt)
        await self.db.commit()

    async def get_item_by_id(
        self,
        *,
        meal_plan_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> MealPlanItem | None:
        stmt = select(MealPlanItem).where(
            MealPlanItem.id == item_id,
            MealPlanItem.meal_plan_id == meal_plan_id,
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_item_by_slot(
        self,
        *,
        meal_plan_id: uuid.UUID,
        planned_date: date,
        meal_type: str,
        exclude_item_id: uuid.UUID | None = None,
    ) -> MealPlanItem | None:
        stmt = select(MealPlanItem).where(
            MealPlanItem.meal_plan_id == meal_plan_id,
            MealPlanItem.planned_date == planned_date,
            MealPlanItem.meal_type == normalize_meal_type(meal_type),
        )

        if exclude_item_id is not None:
            stmt = stmt.where(MealPlanItem.id != exclude_item_id)

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def add_item(
        self,
        *,
        meal_plan_id: uuid.UUID,
        data: MealPlanItemCreate,
    ) -> MealPlanItem:
        item = MealPlanItem(
            meal_plan_id=meal_plan_id,
            recipe_id=data.recipe_id,
            planned_date=data.planned_date,
            meal_type=normalize_meal_type(data.meal_type),
        )

        self.db.add(item)

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise MealPlanItemSlotConflictError from exc

        await self.db.refresh(item)

        return item

    async def update_item(
        self,
        *,
        item: MealPlanItem,
        data: MealPlanItemUpdate,
    ) -> MealPlanItem:
        update_data = data.model_dump(exclude_unset=True)

        if "recipe_id" in update_data and data.recipe_id is not None:
            item.recipe_id = data.recipe_id

        if "planned_date" in update_data and data.planned_date is not None:
            item.planned_date = data.planned_date

        if "meal_type" in update_data and data.meal_type is not None:
            item.meal_type = normalize_meal_type(data.meal_type)

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise MealPlanItemSlotConflictError from exc

        await self.db.refresh(item)

        return item

    async def delete_item(self, item_id: uuid.UUID) -> None:
        stmt = delete(MealPlanItem).where(MealPlanItem.id == item_id)

        await self.db.execute(stmt)
        await self.db.commit()
