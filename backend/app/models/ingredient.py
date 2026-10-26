import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.ddl import ingredient_identity_v1 as identity
from app.db.ingredient_identity import register_identity_ddl


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    nutrition_value = relationship(
        "NutritionValue",
        back_populates="ingredient",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(identity.CHECK_EXPRESSION, name=identity.CHECK),
        Index(identity.INDEX, func.public.mealio_ingredient_bits_v1(name), unique=True),
    )

    user_ingredients = relationship(
        "UserIngredient",
        back_populates="ingredient",
    )

    recipe_ingredients = relationship(
        "RecipeIngredient",
        back_populates="ingredient",
    )


register_identity_ddl(Ingredient.__table__)


class NutritionValue(Base):
    __tablename__ = "nutrition_values"

    __table_args__ = (
        CheckConstraint(
            "portion_g BETWEEN 0.01 AND 999999.99",
            name="ck_nutrition_values_portion_g_bounds",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    calories: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )

    protein_g: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    carbs_g: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    fat_g: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    portion_g: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
        default=Decimal("100"),
        server_default="100",
    )

    ingredient = relationship(
        "Ingredient",
        back_populates="nutrition_value",
    )


class UserIngredient(Base):
    __tablename__ = "user_ingredients"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "ingredient_id",
            name="uq_user_ingredient",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
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
        default=Decimal("0"),
        server_default="0",
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    user = relationship(
        "User",
        back_populates="user_ingredients",
    )

    ingredient = relationship(
        "Ingredient",
        back_populates="user_ingredients",
    )
