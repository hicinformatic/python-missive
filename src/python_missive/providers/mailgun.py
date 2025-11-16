"""Mailgun email provider."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Dict, Optional, Tuple

from ..status import MissiveStatus
from .base import BaseProvider


class MailgunProvider(BaseProvider):
    """Mailgun provider (Email only)."""

    name = "Mailgun"
    display_name = "Mailgun"
    supported_types = ["EMAIL"]
    services = ["email", "email_validation", "email_routing"]
    # Geographic scope
    email_geo = "*"
    config_keys = ["MAILGUN_API_KEY", "MAILGUN_DOMAIN"]
    required_packages = ["mailgun"]
    site_url = "https://www.mailgun.com/"
    status_url = "https://status.mailgun.com/"
    documentation_url = "https://documentation.mailgun.com/"
    description_text = (
        "Transactional email service with advanced validation and routing"
    )

    def send_email(self, **kwargs) -> bool:
        """Send via Mailgun API"""
        is_valid, error = self._validate_and_check_recipient(
            "recipient_email", "Email missing"
        )
        if not is_valid:
            self._update_status(MissiveStatus.FAILED, error_message=error)
            return False

        try:
            # TODO: Integrate with Mailgun
            # import requests
            #
            # api_key = self._config.get('MAILGUN_API_KEY')
            # domain = self._config.get('MAILGUN_DOMAIN')
            #
            # response = requests.post(
            #     f"https://api.mailgun.net/v3/{domain}/messages",
            #     auth=("api", api_key),
            #     data={
            #         "from": self._config.get('DEFAULT_FROM_EMAIL'),
            #         "to": self.missive.recipient_email,
            #         "subject": self.missive.subject,
            #         "text": self.missive.body,
            #         "v:missive_id": str(self.missive.id)
            #     }
            # )
            #
            # external_id = response.json().get('id')

            # Simulation
            external_id = f"mg_{getattr(self.missive, 'id', 'unknown')}"

            self._update_status(
                MissiveStatus.SENT, provider=self.name, external_id=external_id
            )
            self._create_event("sent", "Email sent via Mailgun")

            return True

        except Exception as e:
            return self._handle_send_error(e)

    def validate_webhook_signature(
        self,
        payload: Any,
        headers: Dict[str, str],
        *,
        missive_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Tuple[bool, str]:
        """Validate Mailgun webhook signature."""
        api_key = self._config.get("MAILGUN_API_KEY")
        if not api_key:
            return True, ""

        signature_data = payload.get("signature", {})
        timestamp = signature_data.get("timestamp", "")
        token = signature_data.get("token", "")
        signature = signature_data.get("signature", "")

        expected_signature = hmac.new(
            api_key.encode(), f"{timestamp}{token}".encode(), hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(signature, expected_signature):
            return True, ""
        return False, "Signature does not match"

    def extract_email_missive_id(self, payload: Any) -> Optional[str]:
        """Extract missive ID from Mailgun webhook."""
        if isinstance(payload, dict):
            event_data = payload.get("event-data", {})
            if isinstance(event_data, dict):
                user_variables = event_data.get("user-variables", {})
                if isinstance(user_variables, dict):
                    result = user_variables.get("missive_id")
                    return str(result) if result else None
        return None

    def extract_event_type(self, payload: Any) -> str:
        """Extract event type from Mailgun webhook."""
        if isinstance(payload, dict):
            event_data = payload.get("event-data", {})
            if isinstance(event_data, dict):
                result = event_data.get("event", "unknown")
                return str(result) if result else "unknown"
        return "unknown"

    def get_service_status(self) -> Dict:
        """
        Gets Mailgun status and credits.

        Mailgun charges per email sent.

        Returns:
            Dict with status, credits, etc.
        """
        last_check = self._get_last_check_time()

        return {
            "status": "unknown",
            "is_available": None,
            "services": self.services,
            "credits": {
                "type": "emails",
                "remaining": None,
                "currency": "emails",
                "limit": None,
                "percentage": None,
            },
            "rate_limits": {
                "per_second": 100,
                "per_minute": 6000,
            },
            "sla": {
                "uptime_percentage": 99.99,
            },
            "last_check": last_check,
            "warnings": ["Mailgun API not implemented - uncomment the code"],
            "details": {
                "status_page": "https://status.mailgun.com/",
                "api_docs": (
                    "https://documentation.mailgun.com/en/latest/api-stats.html"
                ),
            },
        }


__all__ = ["MailgunProvider"]
