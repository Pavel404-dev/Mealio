from typing import Protocol

from pydantic import SecretStr


class PasswordResetMailer(Protocol):
    def send_password_reset(
        self,
        *,
        recipient_email: str,
        reset_token: SecretStr,
    ) -> None: ...
