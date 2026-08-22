import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailOtpPurpose(str, Enum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


_EMAIL_OTP_PURPOSE_TYPE = SqlEnum(
    EmailOtpPurpose,
    name="email_otp_purpose",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda enum_type: [purpose.value for purpose in enum_type],
    length=32,
)


class EmailOtpChallenge(Base):
    __tablename__ = "email_otp_challenges"
    __table_args__ = (
        CheckConstraint(
            "failed_attempts >= 0",
            name="ck_email_otp_challenges_failed_attempts_nonnegative",
        ),
        CheckConstraint(
            "send_count >= 1",
            name="ck_email_otp_challenges_send_count_positive",
        ),
        Index(
            "ix_email_otp_challenges_user_purpose_email_created_at",
            "user_id",
            "purpose",
            "target_email",
            "created_at",
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

    purpose: Mapped[EmailOtpPurpose] = mapped_column(
        _EMAIL_OTP_PURPOSE_TYPE,
        nullable=False,
    )

    target_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    code_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )

    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        nullable=False,
    )

    send_count: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        nullable=False,
    )

    last_sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
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
