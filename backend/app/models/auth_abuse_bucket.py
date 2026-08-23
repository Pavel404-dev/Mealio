import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.auth_abuse import AuthAbuseAction, AuthAbuseDimension
from app.db.base import Base


_AUTH_ABUSE_ACTION_TYPE = SqlEnum(
    AuthAbuseAction,
    name="auth_abuse_action",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda enum_type: [action.value for action in enum_type],
    length=64,
)

_AUTH_ABUSE_DIMENSION_TYPE = SqlEnum(
    AuthAbuseDimension,
    name="auth_abuse_dimension",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda enum_type: [dimension.value for dimension in enum_type],
    length=16,
)


class AuthAbuseBucket(Base):
    __tablename__ = "auth_abuse_buckets"
    __table_args__ = (
        CheckConstraint(
            "request_count >= 1",
            name="ck_auth_abuse_buckets_request_count_positive",
        ),
        CheckConstraint(
            "expires_at > window_started_at",
            name="ck_auth_abuse_buckets_window_positive",
        ),
        CheckConstraint(
            "char_length(identifier_digest) = 64",
            name="ck_auth_abuse_buckets_identifier_digest_length",
        ),
        UniqueConstraint(
            "action",
            "dimension",
            "identifier_digest",
            name="uq_auth_abuse_buckets_identity",
        ),
        Index(
            "ix_auth_abuse_buckets_expires_at",
            "expires_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    action: Mapped[AuthAbuseAction] = mapped_column(
        _AUTH_ABUSE_ACTION_TYPE,
        nullable=False,
    )
    dimension: Mapped[AuthAbuseDimension] = mapped_column(
        _AUTH_ABUSE_DIMENSION_TYPE,
        nullable=False,
    )
    identifier_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    request_count: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        nullable=False,
    )
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
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
