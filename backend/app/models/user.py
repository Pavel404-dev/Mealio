import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    full_name: Mapped[str | None] = mapped_column(
        String(255),
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

    auth_sessions = relationship(
        "AuthSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    user_ingredients = relationship(
        "UserIngredient",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    recipes = relationship(
        "Recipe",
        back_populates="created_by_user",
    )

    meal_plans = relationship(
        "MealPlan",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    nutrition_profile = relationship(
        "UserNutritionProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    ai_requests = relationship(
        "RecipeAIRequest",
        back_populates="user",
        cascade="all, delete-orphan",
    )
