"""In-app notification provider mixin without Django dependencies."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ...status import MissiveStatus


class BaseNotificationMixin:
    """In-app notification-specific functionality mixin."""

    def get_notification_service_info(self) -> Dict[str, Any]:
        """Return notification service information. Override in subclasses."""
        return {
            "credits": None,
            "credits_type": "unlimited",
            "is_available": None,
            "limits": {},
            "warnings": [
                "get_notification_service_info() method not implemented for this provider"
            ],
            "channels": [],
            "details": {},
        }

    def check_notification_delivery_status(self, **kwargs) -> Dict[str, Any]:
        """Check notification delivery status. Override in subclasses."""
        return {
            "status": "unknown",
            "delivered_at": None,
            "read_at": None,
            "error_code": None,
            "error_message": "check_notification_delivery_status() method not implemented for this provider",
            "details": {},
        }

    def send_notification(self, **kwargs) -> bool:
        """Send an in-app notification. Override in subclasses."""
        recipient_user = self._get_missive_value("recipient_user")
        if not recipient_user:
            self._update_status(MissiveStatus.FAILED, error_message="No recipient user")
            return False

        raise NotImplementedError(
            f"{self.name} must implement the send_notification() method"
        )

    def format_notification_data(self) -> Dict[str, Any]:
        """Format notification data for client applications."""
        if not self.missive:
            return {}

        metadata = getattr(self.missive, "metadata", {}) or {}

        icon_map = {
            "order": "🛒",
            "invoice": "📄",
            "appointment": "📅",
            "message": "💬",
            "alert": "⚠️",
            "success": "✅",
        }

        notification_type = metadata.get("notification_type", "message")
        icon = icon_map.get(notification_type, "🔔")

        redirect_url = metadata.get("redirect_url", "")

        return {
            "title": getattr(self.missive, "subject", ""),
            "body": getattr(self.missive, "body_text", None)
            or getattr(self.missive, "body", ""),
            "icon": icon,
            "url": redirect_url,
            "priority": getattr(self.missive, "priority", "normal"),
            "metadata": metadata,
        }

    def check_user_notification_preferences(self, user: Any) -> Dict[str, Any]:
        """Return a generic preference structure (override for real data)."""
        return {
            "accepts_notifications": True,
            "channels": ["web"],
            "quiet_hours": False,
            "preferences": {},
        }

    def cancel_notification(self, **kwargs) -> bool:
        """Cancel a scheduled notification (override in subclasses)."""
        return False

    def send_push_notification(self, **kwargs) -> bool:
        """Send a push notification. Override in subclasses."""
        raise NotImplementedError(
            f"{self.name} must implement the send_push_notification() method"
        )

    def cancel_push_notification(self, **kwargs) -> bool:
        """Cancel a scheduled push notification (override in subclasses)."""
        return False

    def check_push_notification_delivery_status(self, **kwargs) -> Dict[str, Any]:
        """Check push notification delivery status. Override in subclasses."""
        return {
            "status": "unknown",
            "delivered_at": None,
            "read_at": None,
            "error_code": None,
            "error_message": "check_push_notification_delivery_status() method not implemented for this provider",
            "details": {},
        }

    def get_push_notification_service_info(self) -> Dict[str, Any]:
        """Return push notification service information. Override in subclasses."""
        return {
            "credits": None,
            "credits_type": "unlimited",
            "is_available": None,
            "limits": {},
            "warnings": [
                "get_push_notification_service_info() method not implemented for this provider"
            ],
            "channels": [],
            "details": {},
        }

    def calculate_push_notification_delivery_risk(
        self, missive: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Calculate delivery risk for push notification. Override in subclasses."""
        return {
            "risk_score": 50,
            "risk_level": "medium",
            "factors": {},
            "recommendations": [
                "calculate_push_notification_delivery_risk() method not implemented for this provider"
            ],
        }

    def validate_notification_webhook_signature(
        self, payload: Any, headers: Dict[str, str]
    ) -> Tuple[bool, str]:
        """Validate notification webhook signature. Override in subclasses."""
        return True, ""

    def handle_notification_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[bool, str, Optional[Any]]:
        """Process notification webhook payload. Override in subclasses."""
        return (
            False,
            "handle_notification_webhook() method not implemented for this provider",
            None,
        )

    def extract_notification_missive_id(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract missive ID from notification webhook payload. Override in subclasses."""
        return None

    def validate_push_notification_webhook_signature(
        self, payload: Any, headers: Dict[str, str]
    ) -> Tuple[bool, str]:
        """Validate push notification webhook signature. Override in subclasses."""
        return True, ""

    def handle_push_notification_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[bool, str, Optional[Any]]:
        """Process push notification webhook payload. Override in subclasses."""
        return (
            False,
            "handle_push_notification_webhook() method not implemented for this provider",
            None,
        )

    def extract_push_notification_missive_id(
        self, payload: Dict[str, Any]
    ) -> Optional[str]:
        """Extract missive ID from push notification webhook payload. Override in subclasses."""
        return None
