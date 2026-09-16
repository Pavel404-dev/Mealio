from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pydantic import SecretStr

from app.integrations.email_verification_otp_mailer import (
    EmailVerificationOtpDeliveryError,
)
from app.integrations.password_reset_otp_mailer import (
    PasswordResetOtpDeliveryError,
)

_MAILTRAP_API_BASE_URL = "https://sandbox.api.mailtrap.io"
_MAILTRAP_API_TIMEOUT_SECONDS = 10


class MailtrapApiDeliveryError(RuntimeError):
    pass


class MailtrapApiMailer:
    def __init__(
        self,
        *,
        api_token: str,
        sandbox_id: int,
        from_email: str,
        verification_url_base: str | None = None,
        reset_url_base: str | None = None,
    ) -> None:
        normalized_token = api_token.strip()
        normalized_from_email = from_email.strip()

        if not normalized_token:
            raise ValueError("Mailtrap API token must not be blank")
        if sandbox_id < 1:
            raise ValueError("Mailtrap sandbox ID must be positive")
        if not normalized_from_email:
            raise ValueError("Mailtrap sender email must not be blank")

        self._api_token = normalized_token
        self._sandbox_id = sandbox_id
        self._from_email = normalized_from_email
        self._verification_url_base = self._validate_optional_url_base(
            verification_url_base,
            label="Email verification URL base",
        )
        self._reset_url_base = self._validate_optional_url_base(
            reset_url_base,
            label="Password reset URL base",
        )

    def send_email_verification(
        self,
        *,
        recipient_email: str,
        verification_token: SecretStr,
    ) -> None:
        if self._verification_url_base is None:
            raise ValueError("Email verification URL base is not configured")

        verification_url = self._build_url(
            self._verification_url_base,
            key="token",
            value=verification_token.get_secret_value(),
        )
        self._send(
            recipient_email=recipient_email,
            subject="Verify your Mealio email",
            text=(
                "Verify your email address to complete your Mealio account "
                "setup.\n\n"
                f"Verify your email: {verification_url}\n\n"
                "If you did not create this account, you can ignore this email."
            ),
        )

    def send_email_verification_otp(
        self,
        *,
        recipient_email: str,
        verification_code: SecretStr,
        expires_at: datetime,
    ) -> None:
        expiration = self._format_expiration(
            expires_at,
            label="Email verification code expiration",
        )
        code = verification_code.get_secret_value()

        try:
            self._send(
                recipient_email=recipient_email,
                subject="Verify your Mealio email",
                text=(
                    "Use this six-digit code to verify your email address in "
                    "Mealio.\n\n"
                    f"{code}\n\n"
                    f"This code expires at {expiration}.\n\n"
                    "If you did not request this code, you can ignore this email."
                ),
            )
        except MailtrapApiDeliveryError:
            raise EmailVerificationOtpDeliveryError(
                "Email verification code delivery failed"
            ) from None

    def send_password_reset(
        self,
        *,
        recipient_email: str,
        reset_token: SecretStr,
    ) -> None:
        if self._reset_url_base is None:
            raise ValueError("Password reset URL base is not configured")

        reset_url = self._build_url(
            self._reset_url_base,
            key="token",
            value=reset_token.get_secret_value(),
        )
        self._send(
            recipient_email=recipient_email,
            subject="Reset your Mealio password",
            text=(
                "We received a request to reset your Mealio password.\n\n"
                f"Reset your password: {reset_url}\n\n"
                "If you did not request this change, you can ignore this email."
            ),
        )

    def send_password_reset_otp(
        self,
        *,
        recipient_email: str,
        reset_code: SecretStr,
        expires_at: datetime,
    ) -> None:
        expiration = self._format_expiration(
            expires_at,
            label="Password reset code expiration",
        )
        code = reset_code.get_secret_value()

        try:
            self._send(
                recipient_email=recipient_email,
                subject="Reset your Mealio password",
                text=(
                    "Use this six-digit code to reset your Mealio password.\n\n"
                    f"{code}\n\n"
                    f"This code expires at {expiration}.\n\n"
                    "If you did not request this change, you can ignore this email."
                ),
            )
        except MailtrapApiDeliveryError:
            raise PasswordResetOtpDeliveryError(
                "Password reset code delivery failed"
            ) from None

    def _send(self, *, recipient_email: str, subject: str, text: str) -> None:
        try:
            response = httpx.post(
                f"{_MAILTRAP_API_BASE_URL}/api/send/{self._sandbox_id}",
                headers={
                    "Api-Token": self._api_token,
                    "User-Agent": "Mealio Backend",
                },
                json={
                    "from": {"email": self._from_email, "name": "Mealio"},
                    "to": [{"email": recipient_email}],
                    "subject": subject,
                    "text": text,
                    "category": "Mealio authentication",
                },
                timeout=_MAILTRAP_API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError):
            raise MailtrapApiDeliveryError("Mailtrap API delivery failed") from None

        if not isinstance(result, dict) or result.get("success") is not True:
            raise MailtrapApiDeliveryError("Mailtrap API delivery failed")

    @staticmethod
    def _build_url(base_url: str, *, key: str, value: str) -> str:
        parts = urlsplit(base_url)
        query = [
            (query_key, query_value)
            for query_key, query_value in parse_qsl(
                parts.query,
                keep_blank_values=True,
            )
            if query_key != key
        ]
        query.append((key, value))
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(query),
                parts.fragment,
            )
        )

    @staticmethod
    def _validate_optional_url_base(value: str | None, *, label: str) -> str | None:
        if value is None:
            return None

        normalized_value = value.strip()
        parts = urlsplit(normalized_value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError(f"{label} must be an absolute HTTP(S) URL")
        return normalized_value

    @staticmethod
    def _format_expiration(expires_at: datetime, *, label: str) -> str:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware")
        return expires_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
