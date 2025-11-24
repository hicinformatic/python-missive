"""Framework-agnostic provider base classes."""

from __future__ import annotations

import csv
from collections.abc import MutableMapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ...status import MissiveStatus

EventLogger = Callable[[Dict[str, Any]], None]


class BaseProviderCommon:
    """Base provider with light helpers, detached from Django."""

    name: str = "Base"
    supported_types: list[str] = []
    services: list[str] = []
    brands: list[str] = []
    config_keys: list[str] = []
    required_packages: list[str] = []
    status_url: Optional[str] = None
    documentation_url: Optional[str] = None
    site_url: Optional[str] = None
    description_text: Optional[str] = None

    def __init__(
        self,
        missive: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        event_logger: Optional[EventLogger] = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        """Initialise the provider with optional missive and config."""
        self.missive = missive
        self._raw_config: Dict[str, Any] = dict(config or {})
        self._config: Dict[str, Any] = self._filter_config(self._raw_config)
        self._config_accessor: Optional["_ConfigAccessor"] = None
        self._event_logger = event_logger or (lambda payload: None)
        self._clock = clock

    def _filter_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the subset of config keys declared by the provider."""
        if not self.config_keys:
            return dict(config)
        return {key: config[key] for key in self.config_keys if key in config}

    def _get_missive_value(self, attribute: str, default: Any = None) -> Any:
        """Retrieve an attribute or zero-argument callable from the missive."""
        if not self.missive:
            return default

        # Security: attribute parameter comes from internal code, not user input
        # This is a private method used only by provider implementations
        value = getattr(self.missive, attribute, default)

        if callable(value):
            try:
                return value()
            except TypeError:
                return default

        return value

    # ------------------------------------------------------------------
    # Capabilities helpers
    # ------------------------------------------------------------------

    def supports(self, missive_type: str) -> bool:
        """Return True if the provider handles the given missive type."""
        return missive_type in self.supported_types

    def configure(
        self, config: Dict[str, Any], *, replace: bool = False
    ) -> "BaseProviderCommon":
        """Update provider configuration (filtered by config_keys)."""
        if replace:
            self._raw_config = dict(config or {})
        else:
            self._raw_config.update(config or {})
        self._config = self._filter_config(self._raw_config)
        if self._config_accessor is not None:
            self._config_accessor.refresh()
        return self

    @property
    def config(self) -> "_ConfigAccessor":
        """Return a proxy to configuration dict, callable for updates."""
        if self._config_accessor is None:
            self._config_accessor = _ConfigAccessor(self)
        return self._config_accessor

    def has_service(self, service: str) -> bool:
        """Return True if the provider exposes the given service name."""
        return service in self.services

    def check_package(self, package_name: str) -> bool:
        """Check if a required package is installed.

        Args:
            package_name: Name of the package to check

        Returns:
            True if the package can be imported, False otherwise
        """
        import importlib

        try:
            importlib.import_module(package_name)
            return True
        except ImportError:
            # Try with hyphens replaced by underscores (e.g., sib-api-v3-sdk -> sib_api_v3_sdk)
            try:
                importlib.import_module(package_name.replace("-", "_"))
                return True
            except ImportError:
                return False

    def check_required_packages(self) -> Dict[str, bool]:
        """Check all required packages and return their installation status.

        Returns:
            Dict mapping package names to their installation status
        """
        return {
            package: self.check_package(package) for package in self.required_packages
        }

    def check_config_keys(
        self, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, bool]:
        """Check if all config_keys are present in the provided configuration.

        Args:
            config: Configuration dict to check (defaults to self._raw_config)

        Returns:
            Dict mapping config key names to their presence status
        """
        if config is None:
            config = self._raw_config
        return {key: key in config for key in self.config_keys}

    def check_package_and_config(
        self, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Check both required packages and configuration keys.

        Args:
            config: Configuration dict to check (defaults to self._raw_config)

        Returns:
            Dict with 'packages' and 'config' keys containing their respective status dicts
        """
        return {
            "packages": self.check_required_packages(),
            "config": self.check_config_keys(config),
        }

    # ------------------------------------------------------------------
    # Missive state helpers
    # ------------------------------------------------------------------

    def _update_status(
        self,
        status: MissiveStatus,
        provider: Optional[str] = None,
        external_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update missive attributes when a lifecycle event occurs."""
        if not self.missive:
            return

        if hasattr(self.missive, "status"):
            self.missive.status = status
        if provider and hasattr(self.missive, "provider"):
            self.missive.provider = provider
        if external_id and hasattr(self.missive, "external_id"):
            self.missive.external_id = external_id
        if error_message and hasattr(self.missive, "error_message"):
            self.missive.error_message = error_message

        clock_fn = getattr(self, "_clock", None)
        timestamp = clock_fn() if callable(clock_fn) else datetime.now(timezone.utc)
        if status == MissiveStatus.SENT and hasattr(self.missive, "sent_at"):
            self.missive.sent_at = timestamp
        elif status == MissiveStatus.DELIVERED and hasattr(
            self.missive, "delivered_at"
        ):
            self.missive.delivered_at = timestamp
        elif status == MissiveStatus.READ and hasattr(self.missive, "read_at"):
            self.missive.read_at = timestamp

        save_method = getattr(self.missive, "save", None)
        if callable(save_method):
            save_method()

    def _create_event(
        self,
        event_type: str,
        description: str = "",
        status: Optional[MissiveStatus] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Notify an external event logger about a provider occurrence."""
        if not self.missive:
            return

        payload = {
            "missive": self.missive,
            "provider": self.name,
            "event_type": event_type,
            "description": description,
            "status": status,
            "metadata": metadata or {},
            "occurred_at": self._clock(),
        }
        self._event_logger(payload)

    def get_status_from_event(self, event_type: str) -> Optional[MissiveStatus]:
        """Map a raw provider event name to a MissiveStatus."""
        event_mapping = {
            "delivered": MissiveStatus.DELIVERED,
            "opened": MissiveStatus.READ,
            "clicked": MissiveStatus.READ,
            "read": MissiveStatus.READ,
            "bounced": MissiveStatus.FAILED,
            "failed": MissiveStatus.FAILED,
            "rejected": MissiveStatus.FAILED,
            "dropped": MissiveStatus.FAILED,
        }
        return event_mapping.get(event_type.lower())

    # ------------------------------------------------------------------
    # Proofs and service metadata
    # ------------------------------------------------------------------

    def get_proofs_of_delivery(self, service_type: Optional[str] = None) -> list:
        """Return delivery proofs for the missive (override in subclasses)."""
        if not self.missive:
            return []

        service_type = service_type or self._detect_service_type()
        return []

    def _detect_service_type(self) -> str:
        """Infer service type from the missive object."""
        if not self.missive or not hasattr(self.missive, "missive_type"):
            return "unknown"

        missive_type = getattr(self.missive, "missive_type")

        if missive_type == "LRE":
            return "lre"
        if missive_type == "POSTAL":
            if getattr(self.missive, "is_registered", False):
                if getattr(self.missive, "requires_signature", False):
                    return "postal_signature"
                return "postal_registered"
            return "postal"
        if missive_type == "POSTAL_REGISTERED":
            if getattr(self.missive, "requires_signature", False):
                return "postal_signature"
            return "postal_registered"
        if missive_type == "EMAIL":
            if getattr(self.missive, "is_registered", False):
                return "email_ar"
            return "email"
        if missive_type == "SMS":
            return "sms"
        if missive_type == "BRANDED":
            return self.name.lower()
        if missive_type == "RCS":
            return "rcs"

        return str(missive_type).lower()

    def list_available_proofs(self) -> Dict[str, bool]:
        """Return proof availability keyed by service type."""
        if not self.missive:
            return {}

        service_type = self._detect_service_type()
        proof_services = {"lre", "postal_registered", "postal_signature", "email_ar"}
        return {service_type: service_type in proof_services}

    def check_service_availability(self) -> Dict[str, Any]:
        """Return lightweight service availability information."""
        return {
            "is_available": None,
            "response_time_ms": 0,
            "quota_remaining": None,
            "status": "unknown",
            "last_check": self._get_last_check_time(),
            "warnings": ["Service availability check not implemented"],
        }

    def get_service_status(self) -> Dict[str, Any]:
        """Provide a default status payload for monitoring dashboards."""
        return {
            "status": "unknown",
            "is_available": None,
            "services": list(self.services),
            "credits": {
                "type": "unknown",
                "remaining": None,
                "currency": "",
                "limit": None,
                "percentage": None,
            },
            "last_check": self._get_last_check_time(),
            "warnings": ["get_service_status() not implemented for this provider"],
            "details": {},
        }

    def validate(self) -> tuple[bool, str]:
        """
        Validate provider configuration and missive.

        Returns:
            Tuple of (is_valid, error_message). Default implementation
            checks that required config keys are present.
        """
        if not self.missive:
            return False, "Missive not defined"

        # Check required config keys
        missing_keys = [key for key in self.config_keys if key not in self._raw_config]
        if missing_keys:
            return (
                False,
                f"Missing required configuration keys: {', '.join(missing_keys)}",
            )

        # Enforce geographic scope config per service family
        families = self._detect_service_families()
        missing_geo: list[str] = []
        invalid_geo: list[str] = []
        for family in sorted(families):
            key = f"{family}_geo"
            if key not in self._raw_config:
                missing_geo.append(key)
                continue
            value = self._raw_config.get(key)
            ok, msg = self._validate_geo_config(value)
            if not ok:
                invalid_geo.append(f"{key}: {msg}")

        if missing_geo:
            return (
                False,
                "Missing geographic configuration for services: "
                + ", ".join(missing_geo),
            )
        if invalid_geo:
            return (
                False,
                "Invalid geographic configuration — " + " | ".join(invalid_geo),
            )

        return True, ""

    def _calculate_risk_level(self, risk_score: int) -> str:
        """Calculate risk level from risk score using standard thresholds."""
        if risk_score < 25:
            return "low"
        elif risk_score < 50:
            return "medium"
        elif risk_score < 75:
            return "high"
        else:
            return "critical"

    def _get_last_check_time(self) -> datetime:
        """Get the last check time using the provider's clock."""
        clock = getattr(self, "_clock", None)
        return clock() if callable(clock) else datetime.now(timezone.utc)

    def _handle_send_error(
        self, error: Exception, error_message: Optional[str] = None
    ) -> bool:
        """Handle errors during send operations with consistent error reporting."""
        msg = error_message or str(error)
        self._update_status(MissiveStatus.FAILED, error_message=msg)
        self._create_event("failed", msg)
        return False

    def _validate_and_check_recipient(
        self, recipient_field: str, error_message: str
    ) -> tuple[bool, Optional[str]]:
        """Validate provider and check recipient field exists."""
        is_valid, error = self.validate()
        if not is_valid:
            return False, error

        recipient = self._get_missive_value(recipient_field)
        if not recipient:
            return False, error_message

        return True, None

    def calculate_delivery_risk(self, missive: Optional[Any] = None) -> Dict[str, Any]:
        """Compute a delivery risk score for the given missive."""
        target_missive = missive or self.missive
        if not target_missive:
            return {
                "risk_score": 100,
                "risk_level": "critical",
                "factors": {},
                "recommendations": ["No missive to analyze"],
                "should_send": False,
            }

        factors: Dict[str, Any] = {}
        recommendations = []
        total_risk = 0.0

        missive_type = str(getattr(target_missive, "missive_type", "")).upper()

        if missive_type == "EMAIL":
            email = self._get_missive_value("get_recipient_email") or getattr(
                target_missive, "recipient_email", None
            )
            if email:
                email_validation = self.validate_email(email)
                factors["email_validation"] = email_validation
                total_risk += email_validation["risk_score"] * 0.6
                recommendations.extend(email_validation.get("warnings", []))

        elif missive_type == "SMS":
            if hasattr(self, "calculate_sms_delivery_risk"):
                sms_risk = self.calculate_sms_delivery_risk(target_missive)
                factors["sms_risk"] = sms_risk
                total_risk += sms_risk.get("risk_score", 0) * 0.6
                recommendations.extend(sms_risk.get("recommendations", []))

        elif missive_type == "BRANDED":
            phone = self._get_missive_value("get_recipient_phone") or getattr(
                target_missive, "recipient_phone", None
            )
            if phone:
                phone_validation = self.validate_phone_number(phone)
                factors["phone_validation"] = phone_validation
                total_risk += phone_validation["risk_score"] * 0.6
                recommendations.extend(phone_validation.get("warnings", []))

        elif missive_type == "PUSH_NOTIFICATION":
            if hasattr(self, "calculate_push_notification_delivery_risk"):
                push_risk = self.calculate_push_notification_delivery_risk(
                    target_missive
                )
                factors["push_notification_risk"] = push_risk
                total_risk += push_risk.get("risk_score", 0) * 0.6
                recommendations.extend(push_risk.get("recommendations", []))

        service_check = self.check_service_availability()
        factors["service_availability"] = service_check
        if not service_check.get("is_available"):
            total_risk += 20
            recommendations.append("Service temporarily unavailable")

        risk_score = min(int(total_risk), 100)
        risk_level = self._calculate_risk_level(risk_score)

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "factors": factors,
            "recommendations": recommendations,
            "should_send": risk_score < 70,
        }

    # ------------------------------------------------------------------
    # Geographic scope handling
    # ------------------------------------------------------------------
    _COUNTRIES_INDEX: Dict[str, set] | None = None

    @classmethod
    def _load_countries_index(cls) -> Dict[str, set]:
        if cls._COUNTRIES_INDEX is not None:
            return cls._COUNTRIES_INDEX

        # Find data/countries.csv by walking up from this file location
        csv_path: Path | None = None
        here = Path(__file__).resolve()
        for parent in [here, *here.parents]:
            candidate = None
            if len(parent.parents) >= 5:
                candidate = parent.parents[4] / "data" / "countries.csv"
            if candidate and candidate.exists():
                csv_path = candidate
                break
            # Fallback: project layout where src/ is directly under root
            candidate2 = parent.parent / "data" / "countries.csv"
            if candidate2.exists():
                csv_path = candidate2
                break

        regions: set[str] = set()
        subregions: set[str] = set()
        countries: set[str] = set()
        names: set[str] = set()
        if csv_path and csv_path.exists():
            try:
                with csv_path.open("r", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        cca2 = (row.get("cca2") or "").upper()
                        cca3 = (row.get("cca3") or "").upper()
                        name_common = (row.get("name_common") or "").strip().lower()
                        region = (row.get("region") or "").strip()
                        subregion = (row.get("subregion") or "").strip()
                        if cca2:
                            countries.add(cca2)
                        if cca3:
                            countries.add(cca3)
                        if name_common:
                            names.add(name_common)
                        if region:
                            regions.add(region)
                        if subregion:
                            subregions.add(subregion)
            except Exception:
                # On parsing error, keep empty sets (validation will be lenient)
                pass

        cls._COUNTRIES_INDEX = {
            "regions": regions,
            "subregions": subregions,
            "countries": countries,
            "names": names,
        }
        return cls._COUNTRIES_INDEX

    def _detect_service_families(self) -> set[str]:
        """Map declared services to canonical families for geo config."""
        families: set[str] = set()
        mapping = {
            "postal": "postal",
            "postal_registered": "postal",
            "postal_signature": "postal",
            "email": "email",
            "email_ar": "email",
            "sms": "sms",
            "rcs": "rcs",
            "push_notification": "push",
            "notification": "notification",
            "voice_call": "voice",
            "branded": "branded",
            "lre": "lre",
        }
        for service in self.services:
            fam = mapping.get(service.strip().lower())
            if fam:
                families.add(fam)
        # Also consider supported_types (e.g., POSTAL implies postal)
        type_map = {
            "POSTAL": "postal",
            "EMAIL": "email",
            "SMS": "sms",
            "RCS": "rcs",
            "PUSH_NOTIFICATION": "push",
            "NOTIFICATION": "notification",
            "VOICE_CALL": "voice",
            "BRANDED": "branded",
            "LRE": "lre",
        }
        for t in self.supported_types:
            fam = type_map.get(str(t).upper())
            if fam:
                families.add(fam)
        return families

    @staticmethod
    def _as_tokens(value: Any) -> list[str] | str:
        if isinstance(value, str):
            if value.strip() == "*":
                return "*"
            if "," in value:
                return [v.strip() for v in value.split(",") if v.strip()]
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple)):
            tokens: list[str] = []
            for v in value:
                s = str(v).strip()
                if s:
                    tokens.append(s)
            return tokens
        return []

    def _validate_geo_config(self, value: Any) -> tuple[bool, str]:
        tokens = self._as_tokens(value)
        if tokens == "*":
            return True, ""
        idx = self._load_countries_index()
        regions = idx["regions"]
        subregions = idx["subregions"]
        countries = idx["countries"]
        names = idx["names"]
        invalid: list[str] = []
        for tok in tokens or []:
            t_upper = tok.upper()
            t_lower = tok.lower()
            if (
                t_upper in countries
                or t_lower in names
                or tok in regions
                or tok in subregions
            ):
                continue
            invalid.append(tok)
        if invalid:
            return False, f"unknown tokens: {', '.join(invalid)}"
        return True, ""


class _ConfigAccessor(MutableMapping):
    """Dictionary-like proxy exposing provider configuration with update helper."""

    def __init__(self, provider: BaseProviderCommon) -> None:
        self._provider = provider

    # MutableMapping interface -------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self._provider._config[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._provider.configure({key: value})

    def __delitem__(self, key: str) -> None:
        if key in self._provider._raw_config:
            del self._provider._raw_config[key]
            self._provider._config = self._provider._filter_config(
                self._provider._raw_config
            )
            self.refresh()
        else:  # pragma: no cover - defensive
            raise KeyError(key)

    def __iter__(self):
        return iter(self._provider._config)

    def __len__(self) -> int:
        return len(self._provider._config)

    # Convenience helpers -----------------------------------------------------
    def __call__(
        self, config: Dict[str, Any], *, replace: bool = False
    ) -> BaseProviderCommon:
        """Allow provider.config({...}) to update settings."""
        return self._provider.configure(config, replace=replace)

    def refresh(self) -> None:
        """Ensure external references observe latest configuration."""
        # no-op: MutableMapping view reads live data

    def copy(self) -> Dict[str, Any]:
        return dict(self._provider._config)

    def get(self, key: str, default: Any = None) -> Any:
        return self._provider._config.get(key, default)

    def __repr__(self) -> str:  # pragma: no cover - repr only
        return repr(self._provider._config)
