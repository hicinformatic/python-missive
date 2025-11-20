"""Maileva provider for postal mail and registered mail."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from ..status import MissiveStatus
from .base import BaseProvider


class MailevaProvider(BaseProvider):
    """
    Maileva provider (Docaposte/La Poste group).

    Maileva is a subsidiary of Docaposte (La Poste group) offering
    electronic postal mail services for businesses.

    Supports:
    - Postal mail (simple, registered)
    - Registered mail with signature
    - Document archiving
    """

    name = "Maileva"
    display_name = "Maileva"
    supported_types = ["POSTAL", "LRE"]
    services = [
        "postal",  # Simple mail
        "postal_registered",  # Registered mail
        "postal_signature",  # Registered mail with signature
        "archiving",  # Document archiving
    ]
    # Geographic scopes per service family
    postal_geo = ["FR"]  # Postal mail limited to France
    lre_geo = ["FR"]  # LRE limited to France
    config_keys = [
        "MAILEVA_CLIENTID",
        "MAILEVA_SECRET",
        "MAILEVA_USERNAME",
        "MAILEVA_PASSWORD",
    ]
    required_packages = ["requests"]
    site_url = "https://www.maileva.com/"
    documentation_url = "https://www.maileva.com/developpeur"
    description_text = "Electronic postal mail and registered mail services"

    # API endpoints
    API_BASE_PRODUCTION = "https://api.maileva.com"
    API_BASE_SANDBOX = "https://api.sandbox.maileva.net"
    AUTH_BASE_PRODUCTION = "https://connexion.maileva.com"
    AUTH_BASE_SANDBOX = "https://connexion.sandbox.maileva.net"

    def _get_api_base(self) -> str:
        """Get API base URL based on sandbox mode."""
        sandbox = self._config.get("MAILEVA_SANDBOX", False)
        return self.API_BASE_SANDBOX if sandbox else self.API_BASE_PRODUCTION

    def _get_auth_base(self) -> str:
        """Get authentication base URL based on sandbox mode."""
        sandbox = self._config.get("MAILEVA_SANDBOX", False)
        return self.AUTH_BASE_SANDBOX if sandbox else self.AUTH_BASE_PRODUCTION

    def _get_access_token(self) -> Optional[str]:
        """
        Get OAuth access token from Maileva.

        Maileva uses OAuth 2.0 with client credentials flow.
        """
        try:
            import requests

            auth_url = f"{self._get_auth_base()}/auth/realms/services/protocol/openid-connect/token"
            client_id = self._config.get("MAILEVA_CLIENTID")
            client_secret = self._config.get("MAILEVA_SECRET")
            username = self._config.get("MAILEVA_USERNAME")
            password = self._config.get("MAILEVA_PASSWORD")

            if not all([client_id, client_secret, username, password]):
                return None

            # OAuth 2.0 client credentials + resource owner password credentials
            response = requests.post(
                auth_url,
                data={
                    "grant_type": "password",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "username": username,
                    "password": password,
                },
                timeout=10,
            )
            response.raise_for_status()
            token_data = response.json()
            return token_data.get("access_token")

        except Exception as e:
            self._create_event("error", f"Failed to get access token: {e}")
            return None

    def send_postal(self, **kwargs) -> bool:
        """Send postal mail via Maileva API."""
        # Validation
        is_valid, error = self.validate()
        if not is_valid:
            self._update_status(MissiveStatus.FAILED, error_message=error)
            return False

        if not self._get_missive_value("recipient_address"):
            self._update_status(MissiveStatus.FAILED, error_message="Address missing")
            return False

        try:
            import requests

            access_token = self._get_access_token()
            if not access_token:
                self._update_status(
                    MissiveStatus.FAILED, error_message="Failed to authenticate"
                )
                return False

            api_base = self._get_api_base()
            is_registered = getattr(self.missive, "is_registered", False)
            requires_signature = getattr(self.missive, "requires_signature", False)

            # Choose API version based on service type
            if is_registered or requires_signature:
                # Registered mail API v4
                sendings_url = f"{api_base}/registered_mail/v4/sendings"
            else:
                # Simple mail API v2
                sendings_url = f"{api_base}/mail/v2/sendings"

            # Create sending
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # Build sending payload
            recipient_address = self._get_missive_value("recipient_address", "")
            address_lines = recipient_address.split("\n") if recipient_address else []

            sending_data = {
                "sender": {
                    "name": self._config.get("MAILEVA_SENDER1", ""),
                    "address_line_2": self._config.get("MAILEVA_SENDER2", ""),
                    "address_line_4": self._config.get("MAILEVA_SENDER4", ""),
                    "address_line_6": self._config.get("MAILEVA_SENDER6", ""),
                    "country_code": self._config.get("MAILEVA_SENDERC", "FR"),
                },
                "recipient": {
                    "name": address_lines[0] if address_lines else "",
                    "address": "\n".join(address_lines[1:]) if len(address_lines) > 1 else "",
                },
                "options": {
                    "color_printing": self._config.get("MAILEVA_COLOR_PRINTING", False),
                    "duplex_printing": self._config.get("MAILEVA_DUPLEX_PRINTING", "on"),
                    "optional_address_sheet": self._config.get(
                        "MAILEVA_OPTIONAL_ADDRESS_SHEET", "on"
                    ),
                },
            }

            # TODO: Add document upload
            # TODO: Add recipient details
            # TODO: Submit sending

            # Simulation for now
            external_id = f"mv_{getattr(self.missive, 'id', 'unknown')}"

            letter_type = "registered" if is_registered else "simple"
            if requires_signature:
                letter_type += " with signature"

            self._update_status(
                MissiveStatus.SENT, provider=self.name, external_id=external_id
            )
            self._create_event("sent", f"{letter_type} letter sent via Maileva")

            return True

        except Exception as e:
            self._update_status(MissiveStatus.FAILED, error_message=str(e))
            self._create_event("failed", str(e))
            return False

    def validate_webhook_signature(
        self,
        payload: Any,
        headers: Dict[str, str],
        *,
        missive_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Tuple[bool, str]:
        """Validate Maileva webhook signature."""
        # TODO: Implement according to Maileva webhook documentation
        # Maileva webhooks may use HMAC or OAuth signature
        return True, ""

    def extract_missive_id(
        self, payload: Any, *, missive_type: Optional[str] = None, **kwargs: Any
    ) -> Optional[str]:
        """Extract missive ID from Maileva webhook."""
        if isinstance(payload, dict):
            result = (
                payload.get("sending_id")
                or payload.get("reference")
                or payload.get("id")
            )
            return str(result) if result else None
        return None

    def extract_event_type(self, payload: Any) -> str:
        """Extract event type from Maileva webhook."""
        if isinstance(payload, dict):
            result = payload.get("status") or payload.get("event_type") or "unknown"
            return str(result) if result else "unknown"
        return "unknown"

    def get_proofs_of_delivery(self, service_type: Optional[str] = None) -> list:
        """
        Get all Maileva proofs.

        Maileva generates:
        - Deposit proof (global_deposit_proofs)
        - Delivery proof (if registered)
        - Signature proof (if signature required)
        """
        if not self.missive:
            return []

        external_id = getattr(self.missive, "external_id", None)
        if not external_id or not str(external_id).startswith("mv_"):
            return []

        try:
            import requests

            access_token = self._get_access_token()
            if not access_token:
                return []

            api_base = self._get_api_base()
            sending_id = str(external_id).replace("mv_", "")

            # Get deposit proofs
            proofs_url = f"{api_base}/registered_mail/v4/global_deposit_proofs"
            headers = {"Authorization": f"Bearer {access_token}"}

            # TODO: Implement real API call
            # response = requests.get(
            #     proofs_url,
            #     params={"sending_id": sending_id},
            #     headers=headers,
            #     timeout=10,
            # )
            # response.raise_for_status()
            # proofs_data = response.json()

            # Simulation
            clock = getattr(self, "_clock", None)
            sent_at = getattr(self.missive, "sent_at", None) or (
                clock() if callable(clock) else datetime.now(timezone.utc)
            )

            proofs = [
                {
                    "type": "deposit_receipt",
                    "label": "Deposit Proof",
                    "available": True,
                    "url": f"{api_base}/registered_mail/v4/global_deposit_proofs/{sending_id}",
                    "generated_at": sent_at,
                    "expires_at": None,
                    "format": "pdf",
                    "metadata": {
                        "proof_type": "deposit",
                        "provider": "maileva",
                        "sending_id": sending_id,
                    },
                }
            ]

            # Add delivery proof if registered
            if getattr(self.missive, "is_registered", False):
                delivered_at = getattr(self.missive, "delivered_at", None)
                if delivered_at:
                    proofs.append(
                        {
                            "type": "acknowledgment_receipt",
                            "label": "Acknowledgement of Receipt",
                            "available": True,
                            "url": f"{api_base}/registered_mail/v4/sendings/{sending_id}/proofs/ar",
                            "generated_at": delivered_at,
                            "expires_at": None,
                            "format": "pdf",
                            "metadata": {
                                "proof_type": "ar",
                                "provider": "maileva",
                                "sending_id": sending_id,
                            },
                        }
                    )

            return proofs

        except Exception as e:
            self._create_event("error", f"Failed to get proofs: {e}")
            return []

    def get_service_status(self) -> Dict:
        """
        Gets Maileva status and credits.

        Maileva uses prepaid credits and subscription model.

        Returns:
            Dict with status, credits, etc.
        """
        clock = getattr(self, "_clock", None)
        last_check = clock() if callable(clock) else datetime.now(timezone.utc)

        return {
            "status": "unknown",
            "is_available": None,
            "services": self.services,
            "credits": {
                "type": "money",
                "remaining": None,
                "currency": "EUR",
                "limit": None,
                "percentage": None,
            },
            "rate_limits": {
                "per_second": 5,
                "per_minute": 300,
            },
            "sla": {
                "uptime_percentage": 99.5,
            },
            "last_check": last_check,
            "warnings": ["Maileva API not fully implemented - uncomment the code"],
            "details": {
                "refill_url": "https://www.maileva.com/",
                "api_docs": "https://www.maileva.com/developpeur",
                "sandbox_url": "https://secure2.recette.maileva.com/",
            },
        }

    def get_postal_service_info(self) -> Dict[str, Any]:
        """Get postal service information."""
        return {
            "provider": self.name,
            "services": ["postal", "postal_registered", "postal_signature"],
            "max_attachment_size_mb": 10.0,
            "max_attachment_size_bytes": 10 * 1024 * 1024,
            "allowed_attachment_mime_types": [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "image/jpeg",
                "image/png",
            ],
            "geographic_coverage": self.postal_geo,
            "features": [
                "Color printing",
                "Duplex printing",
                "Optional address sheet",
                "Document archiving",
            ],
        }


__all__ = ["MailevaProvider"]

