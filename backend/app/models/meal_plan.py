import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MealPlan(Base):
    __tablename__ = "meal_plans"

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

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
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
        back_populates="meal_plans",
    )

    items = relationship(
        "MealPlanItem",
        back_populates="meal_plan",
        cascade="all, delete-orphan",
    )


class MealPlanItem(Base):
    __tablename__ = "meal_plan_items"

    __table_args__ = (
        UniqueConstraint(
            "meal_plan_id",
            "planned_date",
            "meal_type",
            name="uq_meal_plan_item_slot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    meal_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meal_plans.id", ondelete="CASCADE"),
        nullable=False,
    )

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
    )

    planned_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    meal_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    meal_plan = relationship(
        "MealPlan",
        back_populates="items",
    )

    recipe = relationship(
        "Recipe",
        back_populates="meal_plan_items",
    )
