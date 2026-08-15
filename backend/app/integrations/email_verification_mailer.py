from typing import Protocol

from pydantic import SecretStr


class EmailVerificationMailer(Protocol):
    def send_email_verification(
        self,
        *,
        recipient_email: str,
        verification_token: SecretStr,
    ) -> None: ...
