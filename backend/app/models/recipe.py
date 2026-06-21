import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    instructions: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    diet_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    total_calories: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    total_protein_g: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    total_carbs_g: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    total_fat_g: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    created_by_user = relationship(
        "User",
        back_populates="recipes",
    )

    recipe_ingredients = relationship(
        "RecipeIngredient",
        back_populates="recipe",
        cascade="all, delete-orphan",
    )

    meal_plan_items = relationship(
        "MealPlanItem",
        back_populates="recipe",
    )

    ai_requests = relationship(
        "RecipeAIRequest",
        back_populates="recipe",
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    __table_args__ = (
        UniqueConstraint(
            "recipe_id",
            "ingredient_id",
            name="uq_recipe_ingredient",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
    )

    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=False,
    )

    quantity_g: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    recipe = relationship(
        "Recipe",
        back_populates="recipe_ingredients",
    )

    ingredient = relationship(
        "Ingredient",
        back_populates="recipe_ingredients",
    )
