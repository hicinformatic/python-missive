"""SendGrid email provider."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any, Dict, Optional, Tuple

from ..status import MissiveStatus
from .base import BaseProvider


class SendGridProvider(BaseProvider):
    """SendGrid email provider."""

    name = "SendGrid"
    display_name = "SendGrid"
    supported_types = ["EMAIL"]
    services = ["email", "email_transactional", "email_marketing"]
    config_keys = ["SENDGRID_API_KEY"]
    required_packages = ["sendgrid"]
    site_url = "https://sendgrid.com/"
    status_url = "https://status.sendgrid.com/"
    documentation_url = "https://docs.sendgrid.com/"
    description_text = "Transactional and marketing email (Twilio SendGrid)"

    def send_email(self, **kwargs) -> bool:
        """Sends email via SendGrid API."""
        is_valid, error = self._validate_and_check_recipient(
            "recipient_email", "Email missing"
        )
        if not is_valid:
            self._update_status(MissiveStatus.FAILED, error_message=error)
            return False

        try:
            # response = sg.send(message)
            # external_id = response.headers.get('X-Message-Id')

            # Simulation
            external_id = f"sg_{getattr(self.missive, 'id', 'unknown')}"

            self._update_status(
                MissiveStatus.SENT, provider=self.name, external_id=external_id
            )
            self._create_event("sent", "Email sent via SendGrid")

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
        """Validate SendGrid webhook signature."""
        webhook_key = self._config.get("SENDGRID_WEBHOOK_KEY")
        if not webhook_key:
            return True, ""  # No validation

        sig_header = "HTTP_X_TWILIO_EMAIL_EVENT_WEBHOOK_SIGNATURE"
        signature = headers.get(sig_header, "")
        ts_header = "HTTP_X_TWILIO_EMAIL_EVENT_WEBHOOK_TIMESTAMP"
        timestamp = headers.get(ts_header, "")

        if not signature or not timestamp:
            return False, "Signature or timestamp missing"

        # Reconstruct the signature
        payload_str = json.dumps(payload, separators=(",", ":"))
        signed_payload = timestamp + payload_str

        expected_signature = base64.b64encode(
            hmac.new(
                webhook_key.encode(), signed_payload.encode(), hashlib.sha256
            ).digest()
        ).decode()

        if hmac.compare_digest(signature, expected_signature):
            return True, ""
        return False, "Signature does not match"

    def extract_email_missive_id(self, payload: Any) -> Optional[str]:
        """Extract missive ID from SendGrid webhook."""
        # SendGrid sends an array of events
        if isinstance(payload, list) and len(payload) > 0:
            event = payload[0]
            if isinstance(event, dict):
                result = event.get("missive_id") or event.get("custom_args", {}).get(
                    "missive_id"
                )
                return str(result) if result else None
        elif isinstance(payload, dict):
            result = payload.get("missive_id") or payload.get("custom_args", {}).get(
                "missive_id"
            )
            return str(result) if result else None
        return None

    def extract_event_type(self, payload: Any) -> str:
        """Extract event type from SendGrid webhook."""
        if isinstance(payload, list) and len(payload) > 0:
            event = payload[0]
            if isinstance(event, dict):
                result = event.get("event", "unknown")
                return str(result) if result else "unknown"
        elif isinstance(payload, dict):
            result = payload.get("event", "unknown")
            return str(result) if result else "unknown"
        return "unknown"

    def get_service_status(self) -> Dict:
        """
        Gets SendGrid status and credits.

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
                "per_second": 10,  # Depends on SendGrid plan
                "per_minute": 600,
            },
            "sla": {
                "uptime_percentage": 99.99,  # SLA SendGrid
                "response_time_ms": 100,
            },
            "last_check": last_check,
            "warnings": ["SendGrid API not implemented - uncomment the code"],
            "details": {
                "status_page": "https://status.sendgrid.com/",
                "api_docs": (
                    "https://docs.sendgrid.com/api-reference/"
                    "stats/retrieve-email-statistics"
                ),
            },
        }


__all__ = ["SendGridProvider"]
