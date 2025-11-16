"""Email provider mixin without Django dependencies."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ...status import MissiveStatus


class BaseEmailMixin:
    """Email-specific functionality mixin."""

    def get_email_service_info(self) -> Dict[str, Any]:
        """Return email service information. Override in subclasses."""
        return {
            "credits": None,
            "credits_type": "unlimited",
            "is_available": None,
            "limits": {},
            "warnings": [
                "get_email_service_info() method not implemented for this provider"
            ],
            "reputation": {},
            "details": {},
        }

    def check_email_delivery_status(self, **kwargs) -> Dict[str, Any]:
        """Check email delivery status. Override in subclasses."""
        return {
            "status": "unknown",
            "delivered_at": None,
            "opened_at": None,
            "clicked_at": None,
            "opens_count": 0,
            "clicks_count": 0,
            "bounce_type": None,
            "error_code": None,
            "error_message": "check_email_delivery_status() method not implemented for this provider",
            "details": {},
        }

    def send_email(self, **kwargs) -> bool:
        """Send email. Override in subclasses."""
        recipient_email = self._get_missive_value("get_recipient_email")
        if not recipient_email:
            recipient_email = self._get_missive_value("recipient_email")

        if not recipient_email:
            self._update_status(
                MissiveStatus.FAILED, error_message="No recipient email"
            )
            return False

        raise NotImplementedError(f"{self.name} must implement the send_email() method")

    def validate_email(self, email: str) -> Dict[str, Any]:
        """Validate email and assess delivery risk."""
        warnings: List[str] = []
        details: Dict[str, Any] = {}

        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        is_valid = bool(re.match(email_regex, email))

        if not is_valid:
            return {
                "is_valid": False,
                "is_deliverable": False,
                "risk_score": 100,
                "warnings": ["Invalid email format"],
                "details": {},
            }

        domain = email.split("@")[1].lower()
        details["domain"] = domain

        risk_score = self._calculate_email_risk_score(email, domain, warnings, details)

        return {
            "is_valid": is_valid,
            "is_deliverable": len(warnings) == 0,
            "risk_score": risk_score,
            "warnings": warnings,
            "details": details,
        }

    def _calculate_email_risk_score(
        self, email: str, domain: str, warnings: List[str], details: Dict[str, Any]
    ) -> int:
        """Calculate email risk score (0-100)."""
        score = 0

        if "Disposable domain detected" in warnings:
            score += 80
        if "No MX record found" in warnings:
            score += 60
        if "SMTP server unreachable" in warnings:
            score += 50

        return min(score, 100)

    def test_smtp_server(self, domain: str) -> Dict[str, Any]:
        """Test SMTP server availability and configuration."""
        return {
            "is_reachable": None,
            "mx_records": [],
            "supports_tls": None,
            "smtp_banner": "",
            "response_time_ms": 0,
            "warnings": ["SMTP diagnostics not implemented"],
        }

    def add_attachment_email(self, attachment: Any) -> Dict[str, Any]:
        """
        Prepare an email attachment for a provider.

        Args:
            attachment: Generic attachment object with optional attributes.

        Returns:
            Provider-agnostic attachment payload.
        """
        file_content: Optional[bytes] = None
        file_obj = getattr(attachment, "file", None)
        if file_obj and hasattr(file_obj, "read"):
            try:
                file_content = file_obj.read()
            except Exception:  # pragma: no cover - defensive
                file_content = None

        return {
            "filename": getattr(attachment, "filename", None),
            "content": file_content,
            "url": getattr(attachment, "external_url", None),
            "mime_type": getattr(attachment, "mime_type", None),
        }

    def calculate_spam_score(self, subject: str, body: str) -> Dict[str, Any]:
        """Compute a spam score for email content."""
        score = 0
        triggers: List[str] = []
        recommendations: List[str] = []

        # Placeholder for future heuristics/ML integration

        return {
            "spam_score": score,
            "triggers": triggers,
            "recommendations": recommendations,
        }

    def cancel_email(self, **kwargs) -> bool:
        """Cancel a scheduled email (override in subclasses)."""
        return False

    def calculate_email_delivery_risk(
        self, missive: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Calculate delivery risk for email missives."""
        target_missive = (
            missive if missive is not None else getattr(self, "missive", None)
        )
        if not target_missive:
            return {
                "risk_score": 100,
                "risk_level": "critical",
                "factors": {},
                "recommendations": ["No missive to analyze"],
                "should_send": False,
            }

        factors: Dict[str, Any] = {}
        recommendations: List[str] = []
        total_risk = 0.0

        email = getattr(self, "_get_missive_value", lambda x, d=None: d)(
            "get_recipient_email"
        ) or getattr(target_missive, "recipient_email", None)
        if not email:
            email = getattr(self, "_get_missive_value", lambda x, d=None: d)(
                "recipient_email"
            )

        if not email:
            recommendations.append("Recipient email missing")
            total_risk = 100
        else:
            email_validation = self.validate_email(str(email))
            factors["email_validation"] = email_validation
            total_risk += email_validation.get("risk_score", 0) * 0.6
            recommendations.extend(email_validation.get("warnings", []))

        risk_score = min(int(total_risk), 100)
        risk_level = getattr(
            self,
            "_calculate_risk_level",
            lambda x: (
                "critical"
                if x >= 75
                else "high" if x >= 50 else "medium" if x >= 25 else "low"
            ),
        )(risk_score)

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "factors": factors,
            "recommendations": recommendations,
            "should_send": risk_score < 70,
        }

    def validate_email_webhook_signature(
        self, payload: Any, headers: Dict[str, str]
    ) -> Tuple[bool, str]:
        """Validate email webhook signature. Override in subclasses."""
        return True, ""

    def handle_email_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[bool, str, Optional[Any]]:
        """Process email webhook payload. Override in subclasses."""
        return (
            False,
            "handle_email_webhook() method not implemented for this provider",
            None,
        )

    def extract_email_missive_id(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract missive ID from email webhook payload. Override in subclasses."""
        return None
