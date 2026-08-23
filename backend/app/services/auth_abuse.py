import math
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_abuse import (
    AuthAbuseAction,
    AuthAbuseDimension,
    AuthAbusePolicy,
)
from app.core.config import Settings, get_settings
from app.core.security import hash_auth_abuse_identifier
from app.repositories.auth_abuse_buckets import AuthAbuseBucketsRepository


_CLEANUP_BATCH_SIZE = 100
_DIMENSION_ORDER = {
    AuthAbuseDimension.IP: 0,
    AuthAbuseDimension.EMAIL: 1,
    AuthAbuseDimension.USER: 2,
}


class AuthAbuseConfigurationError(RuntimeError):
    pass


class AuthAbuseLimitExceeded(Exception):
    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__("Authentication abuse limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class AuthAbuseProtectionService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repository = AuthAbuseBucketsRepository(db)

    def _policies_for(
        self,
        *,
        action: AuthAbuseAction,
        identifiers: Mapping[AuthAbuseDimension, str],
    ) -> list[AuthAbusePolicy]:
        policies = [
            policy
            for policy in self.settings.auth_abuse_policies
            if policy.action is action
        ]
        if not policies:
            raise AuthAbuseConfigurationError(
                f"No authentication abuse policies configured for {action.value}"
            )

        missing_dimensions = {
            policy.dimension for policy in policies
        } - identifiers.keys()
        if missing_dimensions:
            missing = ", ".join(
                sorted(dimension.value for dimension in missing_dimensions)
            )
            raise AuthAbuseConfigurationError(
                f"Missing authentication abuse identifiers: {missing}"
            )

        return sorted(
            policies,
            key=lambda policy: _DIMENSION_ORDER[policy.dimension],
        )

    async def enforce(
        self,
        *,
        action: AuthAbuseAction,
        identifiers: Mapping[AuthAbuseDimension, str],
        now: datetime | None = None,
    ) -> None:
        effective_now = now or datetime.now(UTC)
        if effective_now.tzinfo is None or effective_now.utcoffset() is None:
            raise ValueError("Authentication abuse timestamp must be timezone-aware")

        policies = self._policies_for(
            action=action,
            identifiers=identifiers,
        )
        pepper = self.settings.auth_abuse_pepper.get_secret_value()
        digests = {
            policy.dimension: hash_auth_abuse_identifier(
                dimension=policy.dimension,
                identifier=identifiers[policy.dimension],
                abuse_pepper=pepper,
            )
            for policy in policies
        }

        retry_after_seconds: int | None = None
        async with self.db.begin():
            for policy in policies:
                result = await self.repository.consume(
                    action=action,
                    dimension=policy.dimension,
                    identifier_digest=digests[policy.dimension],
                    limit=policy.limit,
                    window_seconds=policy.window_seconds,
                    now=effective_now,
                )
                if result.request_count > policy.limit:
                    retry_after_seconds = max(
                        1,
                        math.ceil((result.expires_at - effective_now).total_seconds()),
                    )
                    break

            await self.repository.delete_expired(
                now=effective_now,
                batch_size=_CLEANUP_BATCH_SIZE,
            )

        if retry_after_seconds is not None:
            raise AuthAbuseLimitExceeded(
                retry_after_seconds=retry_after_seconds,
            )
