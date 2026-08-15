import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr

from app.integrations.password_reset_mailer import PasswordResetMailer

_SMTP_TIMEOUT_SECONDS = 10


class SmtpPasswordResetMailer(PasswordResetMailer):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        starttls: bool,
        reset_url_base: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._starttls = starttls
        self._reset_url_base = self._validate_reset_url_base(reset_url_base)

    def send_password_reset(
        self,
        *,
        recipient_email: str,
        reset_token: SecretStr,
    ) -> None:
        reset_url = self._build_reset_url(reset_token.get_secret_value())
        message = EmailMessage()
        message["Subject"] = "Reset your Mealio password"
        message["From"] = self._from_email
        message["To"] = recipient_email
        message.set_content(
            "We received a request to reset your Mealio password.\n\n"
            f"Reset your password: {reset_url}\n\n"
            "If you did not request this change, you can ignore this email."
        )

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

    def _build_reset_url(self, reset_token: str) -> str:
        parts = urlsplit(self._reset_url_base)
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key != "token"
        ]
        query.append(("token", reset_token))

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
    def _validate_reset_url_base(value: str) -> str:
        normalized_value = value.strip()
        parts = urlsplit(normalized_value)

        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("Password reset URL base must be an absolute HTTP(S) URL")

        return normalized_value
