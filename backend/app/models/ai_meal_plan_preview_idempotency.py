import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIMealPlanPreviewIdempotency(Base):
    __tablename__ = "ai_meal_plan_preview_idempotency"
    __table_args__ = (
        Index(
            "ix_ai_meal_plan_preview_idempotency_user_expiry", "user_id", "expires_at"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
