import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr

from app.integrations.email_verification_mailer import EmailVerificationMailer

_SMTP_TIMEOUT_SECONDS = 10


class SmtpEmailVerificationMailer(EmailVerificationMailer):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        starttls: bool,
        verification_url_base: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._starttls = starttls
        self._verification_url_base = self._validate_verification_url_base(
            verification_url_base
        )

    def send_email_verification(
        self,
        *,
        recipient_email: str,
        verification_token: SecretStr,
    ) -> None:
        verification_url = self._build_verification_url(
            verification_token.get_secret_value()
        )
        message = EmailMessage()
        message["Subject"] = "Verify your Mealio email"
        message["From"] = self._from_email
        message["To"] = recipient_email
        message.set_content(
            "Verify your email address to complete your Mealio account setup.\n\n"
            f"Verify your email: {verification_url}\n\n"
            "If you did not create this account, you can ignore this email."
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

    def _build_verification_url(self, verification_token: str) -> str:
        parts = urlsplit(self._verification_url_base)
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key != "token"
        ]
        query.append(("token", verification_token))

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
    def _validate_verification_url_base(value: str) -> str:
        normalized_value = value.strip()
        parts = urlsplit(normalized_value)

        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError(
                "Email verification URL base must be an absolute HTTP(S) URL"
            )

        return normalized_value
