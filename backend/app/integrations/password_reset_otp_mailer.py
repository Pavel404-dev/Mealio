from datetime import datetime
from typing import Protocol

from pydantic import SecretStr


class PasswordResetOtpDeliveryError(RuntimeError):
    pass


class PasswordResetOtpMailer(Protocol):
    def send_password_reset_otp(
        self,
        *,
        recipient_email: str,
        reset_code: SecretStr,
        expires_at: datetime,
    ) -> None: ...
