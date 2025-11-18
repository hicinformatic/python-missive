"""Postal provider mixin without Django dependencies."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ...status import MissiveStatus


class BasePostalMixin:
    """Postal mail-specific functionality mixin."""

    # Default limit for postal pages
    max_postal_pages: int = 50

    # Allowed MIME types for postal attachments (formats that allow page counting)
    # Empty list = all types allowed
    allowed_attachment_mime_types: list[str] = [
        # PDF documents (standard format with page structure)
        "application/pdf",
        # Microsoft Word documents (with page structure)
        "application/msword",  # .doc
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    ]

    # Allowed page formats for postal documents (empty list = all formats allowed)
    allowed_page_formats: list[str] = [
        "A4",
        "Letter",
        "Legal",
        "A3",
    ]

    def get_postal_service_info(self) -> Dict[str, Any]:
        """Return postal service information. Override in subclasses."""
        return {
            "credits": None,
            "credits_type": "amount",
            "is_available": None,
            "limits": {},
            "warnings": [
                "get_postal_service_info() method not implemented for this provider"
            ],
            "options": [],
            "details": {},
        }

    def check_postal_delivery_status(self, **kwargs) -> Dict[str, Any]:
        """Check postal delivery status. Override in subclasses."""
        return {
            "status": "unknown",
            "delivered_at": None,
            "tracking_events": [],
            "signature_proof": None,
            "error_code": None,
            "error_message": "check_postal_delivery_status() method not implemented for this provider",
            "details": {},
        }

    def send_postal(self, **kwargs) -> bool:
        """Send a postal missive. Override in subclasses."""
        recipient_address = self._get_missive_value("get_recipient_address")
        if not recipient_address:
            recipient_address = self._get_missive_value("recipient_address")

        if not recipient_address:
            self._update_status(MissiveStatus.FAILED, error_message="No postal address")
            return False

        raise NotImplementedError(
            f"{self.name} must implement the send_postal() method"
        )

    def validate_postal_address(self, address: str) -> Dict[str, Any]:
        """Validate a postal address and return basic heuristics."""
        warnings: List[str] = []
        parsed: Dict[str, Any] = {}

        lines = [line.strip() for line in address.split("\n") if line.strip()]

        if len(lines) < 3:
            warnings.append("Address too short (at least 3 lines expected)")

        is_complete = len(lines) >= 3 and not warnings

        return {
            "is_valid": bool(lines),
            "is_complete": is_complete,
            "warnings": warnings,
            "parsed": parsed,
        }

    def calculate_postal_cost(
        self,
        weight_grams: int = 20,
        is_registered: bool = False,
        international: bool = False,
    ) -> Dict[str, Any]:
        """Estimate the cost of a postal mail."""
        if international:
            base_cost = 1.96
            delivery_days = 7
        else:
            if weight_grams <= 20:
                base_cost = 1.29
                delivery_days = 2
            elif weight_grams <= 100:
                base_cost = 1.96
                delivery_days = 1
            else:
                base_cost = 3.15
                delivery_days = 2

        if is_registered:
            base_cost += 4.50

        return {
            "cost": base_cost,
            "format": "registered" if is_registered else "standard",
            "delivery_days": delivery_days,
            "weight_grams": weight_grams,
        }

    def prepare_postal_attachments(
        self, attachments: List[Any]
    ) -> List[Dict[str, Any]]:
        """Prepare attachments for postal delivery."""
        prepared: List[Dict[str, Any]] = []

        for attachment in attachments:
            file_info = {
                "filename": getattr(attachment, "filename", None),
                "order": getattr(attachment, "order", None),
                "mime_type": getattr(attachment, "mime_type", None),
                "url": getattr(attachment, "file_url", None),
            }
            prepared.append(file_info)

        return prepared

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

    def _check_attachment_page_count(
        self, attachment: Any, idx: int
    ) -> tuple[Optional[int], List[str], List[str]]:
        """Check page count for a single attachment."""
        errors: List[str] = []
        warnings: List[str] = []

        page_count = getattr(attachment, "page_count", None)
        if page_count is not None:
            try:
                page_count = int(page_count)
                if page_count > self.max_postal_pages:
                    errors.append(
                        f"Attachment {idx + 1}: {page_count} pages exceeds maximum "
                        f"of {self.max_postal_pages} pages"
                    )
                return page_count, errors, warnings
            except (ValueError, TypeError):
                warnings.append(f"Attachment {idx + 1}: Invalid page_count value")

        return None, errors, warnings

    def _check_attachment_page_format(
        self, attachment: Any, idx: int
    ) -> tuple[List[str], List[str]]:
        """Check page format for a single attachment."""
        errors: List[str] = []
        warnings: List[str] = []

        page_format = getattr(attachment, "page_format", None)
        if page_format:
            if (
                self.allowed_page_formats
                and page_format.upper() not in [
                    fmt.upper() for fmt in self.allowed_page_formats
                ]
            ):
                errors.append(
                    f"Attachment {idx + 1}: Page format '{page_format}' not allowed. "
                    f"Allowed formats: {', '.join(self.allowed_page_formats)}"
                )

        return errors, warnings

    def check_attachments(
        self, attachments: List[Any]
    ) -> Dict[str, Any]:
        """
        Validate postal attachments against size, MIME type, page count, and page format limits.

        Args:
            attachments: List of attachment objects with attributes like:
                - mime_type: MIME type of the file
                - page_count: Number of pages (for documents)
                - page_format: Page format (e.g., "A4", "Letter")
                - size_bytes: File size in bytes (optional)

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
            "total_pages": 0,
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

        total_pages = 0

        for idx, attachment in enumerate(attachments):
            attachment_errors: List[str] = []
            attachment_warnings: List[str] = []

            # Check MIME type
            mime_errors, mime_warnings = self._check_attachment_mime_type(attachment, idx)
            attachment_errors.extend(mime_errors)
            attachment_warnings.extend(mime_warnings)

            # Check page count
            page_count, page_errors, page_warnings = self._check_attachment_page_count(
                attachment, idx
            )
            attachment_errors.extend(page_errors)
            attachment_warnings.extend(page_warnings)

            if page_count is not None:
                total_pages += page_count

            # Check page format
            format_errors, format_warnings = self._check_attachment_page_format(
                attachment, idx
            )
            attachment_errors.extend(format_errors)
            attachment_warnings.extend(format_warnings)

            if attachment_errors:
                errors.extend(attachment_errors)
            if attachment_warnings:
                warnings.extend(attachment_warnings)

            details["attachments_checked"] += 1
            if not attachment_errors:
                details["attachments_valid"] += 1

        # Check total pages across all attachments
        details["total_pages"] = total_pages
        if total_pages > self.max_postal_pages:
            errors.append(
                f"Total pages ({total_pages}) exceeds maximum of {self.max_postal_pages} pages"
            )

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "details": details,
        }

    def cancel_postal(self, **kwargs) -> bool:
        """Cancel a scheduled postal missive (override in subclasses)."""
        return False

    def validate_postal_webhook_signature(
        self, payload: Any, headers: Dict[str, str]
    ) -> Tuple[bool, str]:
        """Validate postal webhook signature. Override in subclasses."""
        return True, ""

    def handle_postal_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[bool, str, Optional[Any]]:
        """Process postal webhook payload. Override in subclasses."""
        return (
            False,
            "handle_postal_webhook() method not implemented for this provider",
            None,
        )

    def extract_postal_missive_id(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract missive ID from postal webhook payload. Override in subclasses."""
        return None
