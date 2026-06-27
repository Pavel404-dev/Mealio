import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserNutritionProfile(Base):
    __tablename__ = "user_nutrition_profiles"

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
