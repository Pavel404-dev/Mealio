import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RecipeAIRequest(Base):
    __tablename__ = "recipe_ai_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="SET NULL"),
        nullable=True,
    )

    prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    ingredients_input: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=True,
    )

    ai_response: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=True,
    )

    model_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="ai_requests",
    )

    recipe = relationship(
        "Recipe",
        back_populates="ai_requests",
    )
