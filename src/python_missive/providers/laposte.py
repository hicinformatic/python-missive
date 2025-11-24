"""La Poste provider for postal mail."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from ..status import MissiveStatus
from .base import BaseProvider


class LaPosteProvider(BaseProvider):
    """
    La Poste provider.

    Supports:
    - Postal mail (simple, registered, with signature)
    - AR Email (Email with electronic acknowledgment of receipt)
    """

    name = "La Poste"
    display_name = "La Poste"
    supported_types = ["POSTAL", "POSTAL_REGISTERED", "EMAIL", "LRE"]
    services = [
        "postal",  # Simple mail
        "postal_registered",  # Registered R1
        "postal_signature",  # Registered R2/R3 with signature
        "email_ar",  # Email with electronic AR
        "colissimo",  # Parcel (future extension)
    ]
    # Geographic scopes per service family
    postal_geo = ["FR"]  # Postal mail limited to France
    email_geo = "*"  # Email AR not geographically limited
    lre_geo = "*"  # LRE not geographically limited
    config_keys = ["LAPOSTE_API_KEY"]
    required_packages = ["requests"]
    site_url = "https://www.laposte.fr/"
    description_text = "Registered mail and AR email sending on French territory"

    def send_postal(self, **kwargs) -> bool:
        """Send postal mail via La Poste API"""
        # Validation
        is_valid, error = self.validate()
        if not is_valid:
            self._update_status(MissiveStatus.FAILED, error_message=error)
            return False

        if not self._get_missive_value("recipient_address"):
            self._update_status(MissiveStatus.FAILED, error_message="Address missing")
            return False

        try:
            # TODO: Integrate with La Poste API
            # import requests
            #
            # api_key = self._config.get('LAPOSTE_API_KEY')
            # address_lines = self.missive.recipient_address.split('\n')
            #
            # response = requests.post(
            #     'https://api.laposte.fr/controladresse/v2/send',
            #     headers={'Authorization': f'Bearer {api_key}'},
            #     json={
            #         'sender': self._config.get('LAPOSTE_SENDER_ADDRESS'),
            #         'recipient': {
            #             'name': address_lines[0] if address_lines else '',
            #             'address': '\n'.join(address_lines[1:]),
            #         },
            #         'content': self.missive.body,
            #         'options': {
            #             'registered': self.missive.is_registered,
            #             'signature_required': self.missive.requires_signature,
            #         }
            #     }
            # )
            #
            # result = response.json()
            # external_id = result.get('tracking_number')

            # Simulation
            external_id = f"lp_{getattr(self.missive, 'id', 'unknown')}"

            letter_type = (
                "registered"
                if getattr(self.missive, "is_registered", False)
                else "simple"
            )
            if getattr(self.missive, "requires_signature", False):
                letter_type += " with signature"

            self._update_status(
                MissiveStatus.SENT, provider=self.name, external_id=external_id
            )
            self._create_event("sent", f"{letter_type} letter sent via La Poste")

            return True

        except Exception as e:
            self._update_status(MissiveStatus.FAILED, error_message=str(e))
            self._create_event("failed", str(e))
            return False

    def send_email(self, **kwargs) -> bool:
        """
        Send an AR email (with acknowledgement of receipt) via La Poste.
        La Poste offers an electronic registered email service.
        """
        # Validation
        is_valid, error = self.validate()
        if not is_valid:
            self._update_status(MissiveStatus.FAILED, error_message=error)
            return False

        if not self._get_missive_value("recipient_email"):
            self._update_status(MissiveStatus.FAILED, error_message="Email missing")
            return False

        try:
            # TODO: Integrate with La Poste Email AR
            # Simulation
            external_id = f"lp_email_{getattr(self.missive, 'id', 'unknown')}"

            self._update_status(
                MissiveStatus.SENT,
                provider=f"{self.name} Email AR",
                external_id=external_id,
            )
            self._create_event("sent", "AR email sent via La Poste")

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
        """Validate La Poste webhook signature."""
        # To be implemented according to La Poste API documentation
        return True, ""

    def extract_missive_id(
        self, payload: Any, *, missive_type: Optional[str] = None, **kwargs: Any
    ) -> Optional[str]:
        """Extract missive ID from La Poste webhook."""
        if isinstance(payload, dict):
            result = payload.get("reference") or payload.get("tracking_number")
            return str(result) if result else None
        return None

    def extract_event_type(self, payload: Any) -> str:
        """Extract event type from La Poste webhook."""
        if isinstance(payload, dict):
            result = payload.get("status", "unknown")
            return str(result) if result else "unknown"
        return "unknown"

    def get_proofs_of_delivery(self, service_type: Optional[str] = None) -> list:
        """
        Get all La Poste proofs.

        La Poste generates several documents according to service:
        - Simple mail: Deposit proof
        - Registered mail R1: Deposit proof + AR + delivery notice
        - Registered mail R2/R3: Deposit proof + AR + signature + scanned copy
        - AR Email: Electronic acknowledgement of receipt

        TODO: Implement via La Poste API
        """
        if not self.missive:
            return []

        external_id = getattr(self.missive, "external_id", None)
        if not external_id or not str(external_id).startswith("lp_"):
            return []

        # Determine the service type
        if not service_type:
            missive_type = getattr(self.missive, "missive_type", "")
            if missive_type == "EMAIL":
                service_type = "email_ar"
            elif getattr(self.missive, "requires_signature", False):
                service_type = "postal_signature"
            elif getattr(self.missive, "is_registered", False):
                service_type = "postal_registered"
            else:
                service_type = "postal"

        # TODO: Real API call

        # Simulation
        clock = getattr(self, "_clock", None)
        sent_at = getattr(self.missive, "sent_at", None) or (
            clock() if callable(clock) else datetime.now(timezone.utc)
        )
        tracking_number = str(external_id).replace("lp_", "")
        proofs = []

        # 1. Deposit proof (always available)
        proofs.append(
            {
                "type": "deposit_receipt",
                "label": "Deposit Proof",
                "available": True,
                "url": f"https://www.laposte.fr/suivi/proof/deposit/{tracking_number}.pdf",
                "generated_at": sent_at,
                "expires_at": None,
                "format": "pdf",
                "metadata": {
                    "proof_type": "deposit",
                    "provider": "laposte",
                    "tracking_number": tracking_number,
                },
            }
        )

        # 2. Document copy (if postal mail)
        if "postal" in service_type:
            proofs.append(
                {
                    "type": "document_copy",
                    "label": "Mail Copy",
                    "available": True,
                    "url": f"https://www.laposte.fr/suivi/document/{tracking_number}.pdf",
                    "generated_at": sent_at,
                    "expires_at": None,
                    "format": "pdf",
                    "metadata": {
                        "document_type": "copy",
                        "provider": "laposte",
                    },
                }
            )

        # 3. AR (if registered and delivered)
        if getattr(self.missive, "is_registered", False):
            delivered_at = getattr(self.missive, "delivered_at", None)
            if delivered_at:
                proofs.append(
                    {
                        "type": "acknowledgment_receipt",
                        "label": "Acknowledgement of Receipt",
                        "available": True,
                        "url": f"https://www.laposte.fr/suivi/ar/{tracking_number}.pdf",
                        "generated_at": delivered_at,
                        "expires_at": None,
                        "format": "pdf",
                        "metadata": {
                            "ar_type": (
                                "R1"
                                if not getattr(
                                    self.missive, "requires_signature", False
                                )
                                else "R2/R3"
                            ),
                            "delivery_date": (
                                delivered_at.isoformat()
                                if hasattr(delivered_at, "isoformat")
                                else str(delivered_at)
                            ),
                            "provider": "laposte",
                        },
                    }
                )

        return proofs

    def get_service_status(self) -> Dict:
        """
        Gets La Poste status and credits.

        La Poste uses prepaid credits.

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
                "per_second": 2,
                "per_minute": 120,
            },
            "sla": {
                "uptime_percentage": 99.9,
            },
            "last_check": last_check,
            "warnings": ["La Poste API not implemented - uncomment the code"],
            "details": {
                "refill_url": "https://developer.laposte.fr/",
                "api_docs": "https://developer.laposte.fr/products",
            },
        }


__all__ = ["LaPosteProvider"]
