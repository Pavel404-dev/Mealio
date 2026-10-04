import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserNutritionProfile(Base):
    __tablename__ = "user_nutrition_profiles"

    __table_args__ = (
        CheckConstraint("sex IN ('male', 'female')", name="ck_nutrition_profile_sex"),
        CheckConstraint(
            "birth_date >= DATE '1900-01-01' AND birth_date <= (clock_timestamp() AT TIME ZONE 'UTC')::date",
            name="ck_nutrition_profile_birth_date",
        ),
        CheckConstraint(
            "height_cm BETWEEN 50.0 AND 250.0", name="ck_nutrition_profile_height_cm"
        ),
        CheckConstraint(
            "weight_kg BETWEEN 10.00 AND 500.00", name="ck_nutrition_profile_weight_kg"
        ),
        CheckConstraint(
            "activity_level IN ('sedentary', 'lightly_active', 'moderately_active', 'very_active', 'extra_active')",
            name="ck_nutrition_profile_activity_level",
        ),
        CheckConstraint(
            "max_cooking_time_minutes BETWEEN 1 AND 480",
            name="ck_nutrition_profile_max_cooking_time_minutes",
        ),
        CheckConstraint(
            "weekly_food_budget_amount BETWEEN 0.01 AND 1000000.00",
            name="ck_nutrition_profile_weekly_food_budget_amount",
        ),
        CheckConstraint(
            "char_length(budget_currency) = 3 AND budget_currency ~ '^[A-Z]{3}$'",
            name="ck_nutrition_profile_budget_currency",
        ),
        CheckConstraint(
            "(weekly_food_budget_amount IS NULL) = (budget_currency IS NULL)",
            name="ck_nutrition_profile_budget_pair",
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
        unique=True,
        nullable=False,
    )

    goal: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="maintain",
        server_default="maintain",
    )

    diet_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    daily_calories_target: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    daily_protein_target_g: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    daily_carbs_target_g: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    daily_fat_target_g: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    allergies: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    disliked_ingredients: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    preferred_meals_per_day: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    sex: Mapped[str | None] = mapped_column(String(6), nullable=True)

    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)

    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    activity_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    max_cooking_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    weekly_food_budget_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 2), nullable=True
    )

    budget_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

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
        back_populates="nutrition_profile",
    )
