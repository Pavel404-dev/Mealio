import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage

from pydantic import SecretStr

from app.integrations.password_reset_otp_mailer import (
    PasswordResetOtpDeliveryError,
    PasswordResetOtpMailer,
)

_SMTP_TIMEOUT_SECONDS = 10


class SmtpPasswordResetOtpMailer(PasswordResetOtpMailer):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        starttls: bool,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._starttls = starttls

    def send_password_reset_otp(
        self,
        *,
        recipient_email: str,
        reset_code: SecretStr,
        expires_at: datetime,
    ) -> None:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("Password reset code expiration must be timezone-aware")

        code = reset_code.get_secret_value()
        expiration = expires_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        message = EmailMessage()
        message["Subject"] = "Reset your Mealio password"
        message["From"] = self._from_email
        message["To"] = recipient_email
        message.set_content(
            "Use this six-digit code to reset your Mealio password.\n\n"
            f"{code}\n\n"
            f"This code expires at {expiration}.\n\n"
            "If you did not request this change, you can ignore this email."
        )

        try:
            with smtplib.SMTP(
                self._host,
                self._port,
                timeout=_SMTP_TIMEOUT_SECONDS,
            ) as smtp:
                if self._starttls:
                    smtp.starttls(context=ssl.create_default_context())

                if self._username is not None and self._password is not None:
                    smtp.login(self._username, self._password)

                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise PasswordResetOtpDeliveryError(
                "Password reset code delivery failed"
            ) from None
