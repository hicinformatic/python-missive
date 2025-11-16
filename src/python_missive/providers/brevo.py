"""Brevo provider for email and SMS."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..status import MissiveStatus
from .base import BaseProvider


class BrevoProvider(BaseProvider):
    """
    Brevo (ex Sendinblue) provider.

    Supports:
        - Email (transactional/marketing)
        - SMS
    """

    name = "Brevo"
    display_name = "Brevo"
    supported_types = ["EMAIL", "SMS"]
    services = [
        "email",
        "email_transactional",
        "email_marketing",
        "sms",
        "contacts",
        "automation",
    ]
    config_keys = ["BREVO_API_KEY", "BREVO_SMS_SENDER", "BREVO_DEFAULT_FROM_EMAIL"]
    required_packages = ["sib-api-v3-sdk"]
    site_url = "https://www.brevo.com/"
    status_url = "https://status.brevo.com/"
    documentation_url = "https://developers.brevo.com/"
    description_text = "Complete CRM platform (Email, SMS, Marketing automation)"

    # ------------------------------------------------------------------
    # Common helpers
    # ------------------------------------------------------------------

    def _get_sender_email(self) -> Optional[str]:
        return self._config.get("BREVO_DEFAULT_FROM_EMAIL")

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    def send_email(self, **kwargs) -> bool:
        """Simulate email sending via Brevo."""
        risk = self.calculate_email_delivery_risk()
        if not risk.get("should_send", True):
            recommendations = risk.get("recommendations", [])
            error_message = next(
                (rec for rec in recommendations if rec), "Email delivery blocked"
            )
            self._update_status(MissiveStatus.FAILED, error_message=error_message)
            return False

        external_id = f"brevo_email_{getattr(self.missive, 'id', 'unknown')}"
        self._update_status(
            MissiveStatus.SENT, provider=self.name, external_id=external_id
        )
        self._create_event("sent", "Email sent via Brevo")
        return True

    def get_email_service_info(self) -> Dict[str, Any]:
        base = super().get_email_service_info()
        base.update(
            {
                "service": "brevo_email",
                "warnings": base.get("warnings", []),
                "details": {"supports_marketing": True},
            }
        )
        return base

    # ------------------------------------------------------------------
    # SMS
    # ------------------------------------------------------------------

    def send_sms(self, **kwargs) -> bool:
        """Simulate SMS sending via Brevo."""
        risk = self.calculate_sms_delivery_risk()
        if not risk.get("should_send", True):
            recommendations = risk.get("recommendations", [])
            error_message = next(
                (rec for rec in recommendations if rec), "SMS delivery blocked"
            )
            self._update_status(MissiveStatus.FAILED, error_message=error_message)
            return False

        external_id = f"brevo_sms_{getattr(self.missive, 'id', 'unknown')}"
        self._update_status(
            MissiveStatus.SENT, provider=self.name, external_id=external_id
        )
        self._create_event("sent", "SMS sent via Brevo")
        return True

    def get_sms_service_info(self) -> Dict[str, Any]:
        base = super().get_sms_service_info()
        base.update(
            {
                "service": "brevo_sms",
                "warnings": base.get("warnings", []),
                "details": {"supports_unicode": True},
            }
        )
        return base

    # ------------------------------------------------------------------
    # Webhooks / Monitoring (placeholders)
    # ------------------------------------------------------------------

    def validate_webhook_signature(
        self,
        payload: Any,
        headers: Dict[str, str],
        *,
        missive_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Tuple[bool, str]:
        """Validate Brevo webhook signature (not implemented)."""
        return True, ""

    def extract_email_missive_id(self, payload: Any) -> Optional[str]:
        """Extract missive ID from Brevo email webhook payload."""
        if isinstance(payload, dict):
            tag = payload.get("tag", "")
            if isinstance(tag, str) and tag.startswith("missive_"):
                return tag.replace("missive_", "")
        return None

    def extract_sms_missive_id(self, payload: Any) -> Optional[str]:
        """Extract missive ID from Brevo SMS webhook payload."""
        if isinstance(payload, dict):
            tag = payload.get("tag", "")
            if isinstance(tag, str) and tag.startswith("missive_"):
                return tag.replace("missive_", "")
        return None  # type: ignore[no-any-return]

    def extract_event_type(self, payload: Any) -> str:
        """Return Brevo event type from webhook payload."""
        if isinstance(payload, dict):
            result = payload.get("event", "unknown")
            return str(result) if result else "unknown"  # type: ignore[no-any-return]
        return "unknown"

    def get_service_status(self) -> Dict[str, Any]:
        """Return simulated service status/credits."""
        clock = getattr(self, "_clock", None)
        last_check = clock() if callable(clock) else None

        return {
            "status": "unknown",
            "is_available": None,
            "services": self.services,
            "credits": {
                "type": "mixed",
                "email": {
                    "remaining": None,
                    "limit": "unknown",
                },
                "sms": {
                    "remaining": None,
                    "currency": "sms_units",
                },
            },
            "rate_limits": {"per_second": 10},
            "sla": {"uptime_percentage": 99.95},
            "last_check": last_check,
            "warnings": ["Brevo API integration not implemented."],
            "details": {
                "status_page": "https://status.brevo.com/",
                "api_docs": "https://developers.brevo.com/",
            },
        }

    # ------------------------------------------------------------------
    # Risk calculations
    # ------------------------------------------------------------------

    def calculate_email_delivery_risk(
        self, missive: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Assess whether an email can be sent safely via Brevo."""
        target_missive = missive if missive is not None else self.missive
        if not target_missive:
            return {
                "risk_score": 100,
                "risk_level": "critical",
                "factors": {},
                "recommendations": ["No missive to analyze"],
                "should_send": False,
            }

        factors: Dict[str, Any] = {}
        recommendations: list[str] = []
        total_risk = 0.0

        if "BREVO_API_KEY" not in self._config:
            recommendations.append("Missing BREVO_API_KEY in configuration")
            total_risk = 100

        recipient_email = self._get_missive_value("recipient_email")
        if not recipient_email:
            recommendations.append("Recipient email missing")
            total_risk = 100
        else:
            email_validation = self.validate_email(recipient_email)
            factors["email_validation"] = email_validation
            total_risk += email_validation.get("risk_score", 0) * 0.5
            recommendations.extend(email_validation.get("warnings", []))

        sender_email = self._get_sender_email()
        if not sender_email:
            recommendations.append("BREVO_DEFAULT_FROM_EMAIL missing")
            total_risk = max(total_risk, 80)

        service_status = self.get_service_status()
        factors["service_status"] = service_status
        if service_status.get("is_available") is False:
            total_risk += 40
            recommendations.append("Brevo email service currently unavailable")

        risk_score = min(int(total_risk), 100)
        risk_level = self._calculate_risk_level(risk_score)

        should_send = (
            risk_score < 70 and "Recipient email missing" not in recommendations
        )

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "factors": factors,
            "recommendations": recommendations,
            "should_send": should_send,
        }

    def calculate_sms_delivery_risk(
        self, missive: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Assess whether an SMS can be sent safely via Brevo."""
        base_result = super().calculate_sms_delivery_risk(missive)

        if not base_result.get("should_send", True):
            return base_result

        factors = dict(base_result.get("factors", {}))
        recommendations = list(base_result.get("recommendations", []))
        risk_score = float(base_result.get("risk_score", 0))

        if "BREVO_API_KEY" not in self._config:
            recommendations.append("Missing BREVO_API_KEY in configuration")
            base_result.update(
                {
                    "risk_score": 100,
                    "risk_level": "critical",
                    "factors": factors,
                    "recommendations": recommendations,
                    "should_send": False,
                }
            )
            return base_result

        sender = self._config.get("BREVO_SMS_SENDER")
        if not sender:
            recommendations.append("BREVO_SMS_SENDER missing (highly recommended)")
            risk_score = max(risk_score, 60)

        service_status = self.get_service_status()
        factors["service_status"] = service_status
        if service_status.get("is_available") is False:
            risk_score = min(100.0, risk_score + 40)
            recommendations.append("Brevo SMS service currently unavailable")

        risk_level = self._calculate_risk_level(int(risk_score))
        should_send = risk_score < 70

        base_result.update(
            {
                "risk_score": int(risk_score),
                "risk_level": risk_level,
                "factors": factors,
                "recommendations": recommendations,
                "should_send": should_send,
            }
        )
        return base_result


__all__ = ["BrevoProvider"]
