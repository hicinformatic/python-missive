"""Postal provider mixin without Django dependencies."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ...status import MissiveStatus


class BasePostalMixin:
    """Postal mail-specific functionality mixin."""

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
