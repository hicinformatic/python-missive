"""Email provider mixin without Django dependencies."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ...status import MissiveStatus


class BaseEmailMixin:
    """Email-specific functionality mixin."""

    # Default limit for email attachments (in MB)
    max_email_attachment_size_mb: int = 25

    # Allowed MIME types for email attachments (empty list = all types allowed)
    allowed_attachment_mime_types: list[str] = [
        # Documents
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
        "text/plain",
        "text/csv",
        "text/html",
        # Images
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        # Archives
        "application/zip",
        "application/x-rar-compressed",
        "application/x-tar",
        "application/gzip",
    ]

    @property
    def max_email_attachment_size_bytes(self) -> int:
        """Return max attachment size in bytes."""
        return int(self.max_email_attachment_size_mb * 1024 * 1024)

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

    def _check_attachment_mime_type(
        self, attachment: Any, idx: int
    ) -> tuple[List[str], List[str]]:
        """Check MIME type for a single attachment."""
        errors: List[str] = []
        warnings: List[str] = []

        mime_type = getattr(attachment, "mime_type", None)
        if mime_type:
            if (
                self.allowed_attachment_mime_types
                and mime_type not in self.allowed_attachment_mime_types
            ):
                errors.append(
                    f"Attachment {idx + 1}: MIME type '{mime_type}' not allowed. "
                    f"Allowed types: {', '.join(self.allowed_attachment_mime_types)}"
                )
        else:
            warnings.append(f"Attachment {idx + 1}: MIME type not specified")

        return errors, warnings

    def _get_attachment_size(self, attachment: Any) -> Optional[int]:
        """Get attachment size in bytes, trying multiple methods."""
        size_bytes = getattr(attachment, "size_bytes", None)
        if size_bytes is not None:
            return size_bytes

        # Try to get size from file object
        file_obj = getattr(attachment, "file", None)
        if file_obj and hasattr(file_obj, "read"):
            try:
                current_pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
                file_obj.seek(0, 2)  # Seek to end
                size_bytes = file_obj.tell() if hasattr(file_obj, "tell") else None
                file_obj.seek(current_pos)  # Restore position
                return size_bytes
            except Exception:
                pass

        return None

    def _check_attachment_size(
        self, attachment: Any, idx: int, max_size_bytes: int
    ) -> tuple[Optional[int], List[str], List[str]]:
        """Check file size for a single attachment."""
        errors: List[str] = []
        warnings: List[str] = []

        size_bytes = self._get_attachment_size(attachment)
        if size_bytes is not None:
            try:
                size_bytes = int(size_bytes)
                if size_bytes > max_size_bytes:
                    size_mb = size_bytes / (1024 * 1024)
                    max_mb = self.max_email_attachment_size_mb
                    errors.append(
                        f"Attachment {idx + 1}: Size {size_mb:.2f} MB exceeds maximum "
                        f"of {max_mb} MB"
                    )
                return size_bytes, errors, warnings
            except (ValueError, TypeError):
                warnings.append(f"Attachment {idx + 1}: Invalid size_bytes value")
        else:
            warnings.append(f"Attachment {idx + 1}: File size not specified")

        return None, errors, warnings

    def check_attachments(
        self, attachments: List[Any]
    ) -> Dict[str, Any]:
        """
        Validate email attachments against size and MIME type limits.

        Args:
            attachments: List of attachment objects with attributes like:
                - mime_type: MIME type of the file
                - size_bytes: File size in bytes
                - file: File object with read() method (optional)

        Returns:
            Dict with validation results:
                - is_valid: bool
                - errors: List[str] of error messages
                - warnings: List[str] of warning messages
                - details: Dict with per-attachment validation details
        """
        errors: List[str] = []
        warnings: List[str] = []
        details: Dict[str, Any] = {
            "total_size_bytes": 0,
            "attachments_checked": 0,
            "attachments_valid": 0,
        }

        if not attachments:
            return {
                "is_valid": True,
                "errors": [],
                "warnings": [],
                "details": details,
            }

        total_size_bytes = 0
        max_size_bytes = self.max_email_attachment_size_bytes

        for idx, attachment in enumerate(attachments):
            attachment_errors: List[str] = []
            attachment_warnings: List[str] = []

            # Check MIME type
            mime_errors, mime_warnings = self._check_attachment_mime_type(attachment, idx)
            attachment_errors.extend(mime_errors)
            attachment_warnings.extend(mime_warnings)

            # Check file size
            size_bytes, size_errors, size_warnings = self._check_attachment_size(
                attachment, idx, max_size_bytes
            )
            attachment_errors.extend(size_errors)
            attachment_warnings.extend(size_warnings)

            if size_bytes is not None:
                total_size_bytes += size_bytes

            if attachment_errors:
                errors.extend(attachment_errors)
            if attachment_warnings:
                warnings.extend(attachment_warnings)

            details["attachments_checked"] += 1
            if not attachment_errors:
                details["attachments_valid"] += 1

        # Check total size across all attachments
        details["total_size_bytes"] = total_size_bytes
        total_size_mb = total_size_bytes / (1024 * 1024)
        if total_size_bytes > max_size_bytes:
            errors.append(
                f"Total attachment size ({total_size_mb:.2f} MB) exceeds maximum "
                f"of {self.max_email_attachment_size_mb} MB"
            )

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "details": details,
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
