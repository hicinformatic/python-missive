"""Generic mixin for app messaging providers."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ...status import MissiveStatus


class BaseBrandedMixin:
    """Generic mixin for messaging platforms (WhatsApp, Slack, etc.)."""

    def send_branded(self, brand_name: Optional[str] = None, **kwargs) -> bool:
        """Send a branded message by dispatching to send_{brand_name}."""
        target_name = brand_name or getattr(self, "name", None)

        if not target_name:
            self._update_status(
                MissiveStatus.FAILED,
                error_message="Provider name or brand_name missing",
            )
            return False

        method_name = f"send_{str(target_name).lower()}"

        if not hasattr(self, method_name):
            self._update_status(
                MissiveStatus.FAILED,
                error_message=f"{method_name}() method not implemented for this provider",
            )
            return False

        return getattr(self, method_name)(**kwargs)

    def get_branded_service_info(
        self, brand_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return service information for a branded provider."""
        target_name = brand_name or getattr(self, "name", None)

        if not target_name:
            return {
                "credits": None,
                "is_available": None,
                "limits": {},
                "warnings": ["Provider name or brand_name missing"],
                "details": {},
            }

        method_name = f"get_{str(target_name).lower()}_service_info"

        if hasattr(self, method_name):
            return getattr(self, method_name)()

        return {
            "credits": None,
            "is_available": None,
            "limits": {},
            "warnings": [f"{method_name}() method not implemented for this provider"],
            "details": {},
        }

    def check_branded_delivery_status(
        self, brand_name: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Check delivery status for a branded provider."""
        target_name = brand_name or getattr(self, "name", None)

        if not target_name:
            return {
                "status": "unknown",
                "delivered_at": None,
                "read_at": None,
                "error_code": None,
                "error_message": "Provider name or brand_name missing",
                "details": {},
            }

        method_name = f"check_{str(target_name).lower()}_delivery_status"

        if hasattr(self, method_name):
            return getattr(self, method_name)(**kwargs)

        return {
            "status": "unknown",
            "delivered_at": None,
            "read_at": None,
            "error_code": None,
            "error_message": f"{method_name}() method not implemented",
            "details": {},
        }

    def _get_organization_context(self) -> Optional[Dict[str, Any]]:
        """Return relevant organization context from missive metadata."""
        metadata = getattr(self.missive, "metadata", {}) if self.missive else {}
        if not metadata:
            return None

        context_keys = {
            "workspace_id",
            "team_id",
            "channel_id",
            "organization_id",
            "server_id",
            "guild_id",
            "chat_id",
        }

        context = {key: metadata[key] for key in context_keys if key in metadata}
        return context or None

    def cancel_branded(self, brand_name: Optional[str] = None, **kwargs) -> bool:
        """Cancel a branded message."""
        target_name = brand_name or getattr(self, "name", None)

        if not target_name:
            return False

        method_name = f"cancel_{str(target_name).lower()}"
        if hasattr(self, method_name):
            return getattr(self, method_name)(**kwargs)

        return False

    def validate_branded_webhook_signature(
        self, payload: Any, headers: Dict[str, str], brand_name: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Validate branded webhook signature by dispatching to brand-specific method."""
        target_name = brand_name or getattr(self, "name", None)
        if not target_name:
            return True, ""

        method_name = f"validate_{str(target_name).lower()}_webhook_signature"
        if hasattr(self, method_name):
            return getattr(self, method_name)(payload, headers)

        return True, ""

    def handle_branded_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        brand_name: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Any]]:
        """Process branded webhook by dispatching to brand-specific method."""
        target_name = brand_name or getattr(self, "name", None)
        if not target_name:
            return False, "Provider name or brand_name missing", None

        method_name = f"handle_{str(target_name).lower()}_webhook"
        if hasattr(self, method_name):
            return getattr(self, method_name)(payload, headers)

        return False, f"{method_name}() method not implemented", None

    def extract_branded_missive_id(
        self, payload: Dict[str, Any], brand_name: Optional[str] = None
    ) -> Optional[str]:
        """Extract missive ID from branded webhook by dispatching to brand-specific method."""
        target_name = brand_name or getattr(self, "name", None)
        if not target_name:
            return None

        method_name = f"extract_{str(target_name).lower()}_missive_id"
        if hasattr(self, method_name):
            return getattr(self, method_name)(payload)

        return None
