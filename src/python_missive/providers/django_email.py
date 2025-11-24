"""Local email provider emulating Django's email backend without Django."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from ..status import MissiveStatus
from .base import BaseProvider


class DjangoEmailProvider(BaseProvider):
    """Minimal SMTP/file-based email provider compatible with Django configs."""

    name = "django_email"
    display_name = "Django Email Backend"
    supported_types = ["EMAIL"]
    services = ["email"]
    email_geo: Any = "*"
    description_text = (
        "Lightweight email provider delegating to SMTP or local file delivery. "
        "Mimics Django's console/backend behaviour without importing Django."
    )
    required_packages: List[str] = []

    def validate(self) -> Tuple[bool, str]:
        """Ensure minimal configuration is present."""
        # Inject default geo config if not present so BaseProviderCommon validation passes
        if "email_geo" not in self._raw_config:
            self._raw_config["email_geo"] = self.email_geo

        if not self._raw_config.get("DEFAULT_FROM_EMAIL"):
            sender_name = self._get_missive_value("sender") or "noreply@example.com"
            self._raw_config["DEFAULT_FROM_EMAIL"] = (
                sender_name if isinstance(sender_name, str) else "noreply@example.com"
            )

        if not any(
            [
                self._raw_config.get("EMAIL_FILE_PATH"),
                self._raw_config.get("EMAIL_HOST"),
                self._bool_config("EMAIL_SUPPRESS_SEND", False),
            ]
        ):
            return (
                False,
                "Configure EMAIL_HOST/EMAIL_PORT, EMAIL_FILE_PATH, "
                "or set EMAIL_SUPPRESS_SEND to true to record emails locally.",
            )

        return super().validate()

    def send_email(self, **kwargs: Any) -> bool:
        """Send email via SMTP or write it locally, similar to Django's backend."""
        is_valid, error = self._validate_and_check_recipient(
            "get_recipient_email", "Recipient email missing"
        )
        if not is_valid:
            self._update_status(MissiveStatus.FAILED, error_message=error)
            return False

        recipient = self._get_missive_value(
            "get_recipient_email"
        ) or self._get_missive_value("recipient_email")

        if not recipient:
            self._update_status(
                MissiveStatus.FAILED, error_message="Recipient email missing"
            )
            return False

        message = self._build_email_message(recipient)

        try:
            delivery_target = self._deliver(message)
        except (smtplib.SMTPException, OSError, ValueError) as exc:
            return self._handle_send_error(exc)

        external_id = f"django_email_{getattr(self.missive, 'id', 'unknown')}"
        self._update_status(
            MissiveStatus.SENT, provider=self.name, external_id=external_id
        )
        self._create_event("sent", f"Email dispatched via {delivery_target}")
        return True

    def get_email_service_info(self) -> Dict[str, Any]:
        host = self._raw_config.get("EMAIL_HOST") or "localhost"
        return {
            "credits": None,
            "credits_type": "unlimited",
            "is_available": True,
            "limits": {"max_attachment_mb": self.max_email_attachment_size_mb},
            "warnings": [],
            "details": {
                "backend": "smtp" if self._raw_config.get("EMAIL_HOST") else "file",
                "host": host,
                "port": self._raw_config.get("EMAIL_PORT"),
                "use_tls": self._bool_config("EMAIL_USE_TLS", False),
                "use_ssl": self._bool_config("EMAIL_USE_SSL", False),
            },
        }

    def get_service_status(self) -> Dict[str, Any]:
        """Return lightweight status for monitoring screens."""
        backend = "smtp" if self._raw_config.get("EMAIL_HOST") else "file"
        return {
            "status": "operational",
            "is_available": True,
            "services": self.services,
            "credits": {
                "type": "unlimited",
                "remaining": None,
                "currency": "",
                "limit": None,
                "percentage": None,
            },
            "last_check": self._get_last_check_time(),
            "warnings": [],
            "details": {"backend": backend},
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _collect_attachments(self) -> List[Dict[str, Any]]:
        attachments: List[Dict[str, Any]] = []
        source = self._get_missive_value("attachments") or getattr(
            self.missive, "attachments", None
        )
        if not source:
            return attachments

        items: Iterable[Any]
        if isinstance(source, Iterable):
            items = source
        elif hasattr(source, "all"):
            items = source.all()  # type: ignore[assignment]
        else:
            items = []

        for attachment in items:
            try:
                payload = self.add_attachment_email(attachment)
                attachments.append(payload)
            except (OSError, AttributeError, ValueError):
                continue
        return attachments

    def _build_email_message(self, recipient: str) -> EmailMessage:
        subject = str(self._get_missive_value("subject") or "Missive")
        body_html = self._get_missive_value("body") or ""
        body_text = self._get_missive_value("body_text") or (
            body_html if body_html and "<" not in body_html else ""
        )

        message = EmailMessage()
        from_email = str(
            self._raw_config.get("DEFAULT_FROM_EMAIL") or "noreply@example.com"
        )
        message["Subject"] = subject
        message["From"] = from_email
        message["To"] = recipient

        self._set_message_body(message, body_text, body_html)
        self._attach_files_to_message(message)
        return message

    def _set_message_body(
        self, message: EmailMessage, body_text: str, body_html: str
    ) -> None:
        if body_text:
            message.set_content(body_text)
        else:
            message.set_content(" ")

        if body_html and body_html != body_text:
            message.add_alternative(body_html, subtype="html")

    def _attach_files_to_message(self, message: EmailMessage) -> None:
        for attachment in self._collect_attachments():
            content = attachment.get("content")
            if not content:
                continue

            filename = attachment.get("filename") or "attachment"
            mime = attachment.get("mime_type") or "application/octet-stream"
            maintype, _, subtype = mime.partition("/")
            subtype = subtype or "octet-stream"
            message.add_attachment(
                content,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )

    def _deliver(self, message: EmailMessage) -> str:
        if self._bool_config("EMAIL_SUPPRESS_SEND", False):
            path = self._persist_to_file(message)
            return f"local file (suppressed) -> {path}"

        file_path = self._raw_config.get("EMAIL_FILE_PATH")
        if file_path:
            path = self._persist_to_file(message)
            return f"local file -> {path}"

        return self._send_via_smtp(message)

    def _persist_to_file(self, message: EmailMessage) -> str:
        directory = Path(self._raw_config.get("EMAIL_FILE_PATH") or "./sent-emails")
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = self._clock().strftime("%Y%m%d-%H%M%S")
        missive_id = getattr(self.missive, "id", "unknown")
        filename = f"{timestamp}_{missive_id}.eml"
        target = directory / filename
        target.write_text(message.as_string(), encoding="utf-8")
        return str(target)

    def _send_via_smtp(self, message: EmailMessage) -> str:
        host = self._raw_config.get("EMAIL_HOST") or "localhost"
        port = int(self._raw_config.get("EMAIL_PORT") or 25)
        use_ssl = self._bool_config("EMAIL_USE_SSL", False)
        use_tls = self._bool_config("EMAIL_USE_TLS", not use_ssl)
        timeout = float(self._raw_config.get("EMAIL_TIMEOUT") or 10)

        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(host, port, timeout=timeout) as client:
            if not use_ssl and use_tls:
                client.starttls()
            username = self._raw_config.get("EMAIL_HOST_USER")
            password = self._raw_config.get("EMAIL_HOST_PASSWORD")
            if username and password:
                client.login(username, password)
            client.send_message(message)
        return f"smtp://{host}:{port}"

    def _bool_config(self, key: str, default: bool) -> bool:
        value = self._raw_config.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)


__all__ = ["DjangoEmailProvider"]
