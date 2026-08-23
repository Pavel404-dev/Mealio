from datetime import datetime
from typing import Protocol

from pydantic import SecretStr


class EmailVerificationOtpDeliveryError(RuntimeError):
    pass


class EmailVerificationOtpMailer(Protocol):
    def send_email_verification_otp(
        self,
        *,
        recipient_email: str,
        verification_code: SecretStr,
        expires_at: datetime,
    ) -> None: ...
