"""Generic provider behaviour tests."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from python_missive.providers import (BaseProvider, ProviderImportError,
                                      get_provider_name_from_path,
                                      load_provider_class)
from python_missive.status import MissiveStatus


def _load_test_providers():
    """Load MISSIVE_CONFIG_PROVIDERS dynamically from module path."""
    import importlib

    try:
        module = importlib.import_module("tests.test_config")
        return getattr(module, "MISSIVE_CONFIG_PROVIDERS")
    except (ImportError, AttributeError):
        try:
            module = importlib.import_module("test_config")
            return getattr(module, "MISSIVE_CONFIG_PROVIDERS")
        except (ImportError, AttributeError):
            raise ImportError(
                "Could not load MISSIVE_CONFIG_PROVIDERS from tests.test_config or test_config"
            )


MISSIVE_CONFIG_PROVIDERS = _load_test_providers()


def _get_provider_paths() -> list[str]:
    """Extract provider paths from MISSIVE_CONFIG_PROVIDERS dict."""
    return list(MISSIVE_CONFIG_PROVIDERS.keys())


def _get_default_config(provider_name: str) -> Dict[str, Any]:
    """Get default test configuration for a provider by its short name."""
    for provider_path, config in MISSIVE_CONFIG_PROVIDERS.items():
        if get_provider_name_from_path(provider_path) == provider_name:
            result = config.copy()
            return result if isinstance(result, dict) else {}
    return {}


# ---------------------------------------------------------------------------#
# Helper factories
# ---------------------------------------------------------------------------#


class MissiveStub:
    def __init__(self, recipient: Any = None, external_id: Optional[str] = None):
        self.recipient = recipient
        self.status: Optional[MissiveStatus] = None
        self.external_id = external_id
        self.save_called = 0
        self.id = 123
        self.recipient_email: Optional[str] = None
        self.recipient_phone: Optional[str] = None
        self.missive_type: Optional[str] = None
        self.subject = "Subject"
        self.body = "Body"
        self.body_text = None
        self.error_message: Optional[str] = None
        self.provider_options: Optional[Dict[str, Any]] = None

    def save(self) -> None:  # pragma: no cover - simple counter
        self.save_called += 1


class RecipientStub:
    def __init__(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        email: Optional[str] = None,
        address_line1: Optional[str] = None,
        postal_code: Optional[str] = None,
        city: Optional[str] = None,
    ):
        self.metadata = metadata or {}
        self.email = email
        self.address_line1 = address_line1
        self.postal_code = postal_code
        self.city = city


def make_missive(**kwargs: Any) -> MissiveStub:
    missive = MissiveStub(
        recipient=kwargs.get("recipient"),
        external_id=kwargs.get("external_id"),
    )
    for attr in (
        "recipient_email",
        "recipient_phone",
        "missive_type",
        "body",
        "body_text",
    ):
        if attr in kwargs:
            setattr(missive, attr, kwargs[attr])
    missive.provider_options = kwargs.get("provider_options")
    return missive


class SMSWebhookProvider(BaseProvider):
    name = "sms-test"
    supported_types = ["SMS"]
    services = ["sms"]

    def handle_sms_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> tuple[bool, str, Optional[Any]]:
        return True, "handled", payload.get("message_id")

    def validate_sms_webhook_signature(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> tuple[bool, str]:
        return False, "invalid signature"


def _load_provider_registry() -> Dict[str, type[BaseProvider]]:
    """Load provider classes from test configuration."""
    registry: Dict[str, type[BaseProvider]] = {}

    # Load each provider class from configuration (keys are provider paths)
    for provider_path in MISSIVE_CONFIG_PROVIDERS.keys():
        try:
            provider_class = load_provider_class(provider_path)
            provider_name = get_provider_name_from_path(provider_path)
            registry[provider_name] = provider_class  # type: ignore[assignment]
        except ProviderImportError:
            continue

    return registry


_PROVIDER_REGISTRY: Dict[str, type[BaseProvider]] = _load_provider_registry()  # type: ignore[assignment]


def instantiate_provider(
    name: str, config: Optional[Dict[str, Any]] = None, **kwargs: Any
) -> BaseProvider:
    """Instantiate a provider by its short name from the test configuration.

    Config handling:
    - If config is None: uses default test configuration from MISSIVE_CONFIG_PROVIDERS
    - If config is {}: uses empty config (for testing missing config scenarios)
    - If config is a dict with values: merges with defaults (provided takes precedence)
    """
    # Normalize provider name (handle variations like "sms_partner" vs "smspartner")
    normalized_name = name.lower().replace("_", "").replace("-", "")

    # Try exact match first
    if name in _PROVIDER_REGISTRY:
        provider_cls = _PROVIDER_REGISTRY[name]
        provider_name = name
    elif normalized_name in _PROVIDER_REGISTRY:
        provider_cls = _PROVIDER_REGISTRY[normalized_name]
        provider_name = normalized_name
    else:
        # Try to find by partial match
        for key in _PROVIDER_REGISTRY:
            if normalized_name in key or key in normalized_name:
                provider_cls = _PROVIDER_REGISTRY[key]
                provider_name = key
                break
        else:
            raise ValueError(f"Provider '{name}' not found in test configuration")

    # Handle config: None = use defaults, {} = empty, dict = use as-is (no merge)
    # This allows tests to specify exact configs without default interference
    if config is None:
        # Use default config
        final_config = _get_default_config(provider_name)
    else:
        # Use provided config as-is (empty dict or specific values)
        final_config = config

    return provider_cls(config=final_config, **kwargs)


# ---------------------------------------------------------------------------#
# Scenario helpers
# ---------------------------------------------------------------------------#


def _normalise_config(
    config: Optional[Dict[str, Any]], override: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Return a shallow copy of configuration dict.

    If config is None, returns None (to use defaults).
    If config is {}, returns {} (for empty config).
    If override is provided, merges it into config.
    """
    if config is None:
        if override:
            return dict(override)
        return None
    result = dict(config)
    if override:
        result.update(override)
    return result


def _build_missive_kwargs(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert raw missive configuration into kwargs for make_missive()."""
    missive_kwargs = dict(raw)
    recipient_kwargs = missive_kwargs.pop("recipient_kwargs", None)
    if recipient_kwargs is not None:
        missive_kwargs["recipient"] = RecipientStub(**recipient_kwargs)
    return missive_kwargs


# ---------------------------------------------------------------------------#
# Generic test functions (called dynamically via dev.py test_providers)
# ---------------------------------------------------------------------------#


def test_provider_method() -> None:
    """Generic test function that reads parameters from environment variables.

    Called via: dev.py test_providers <provider> <service> <method>
    Special case: dev.py test_providers <provider> check_package_and_config
    """
    import os

    provider_name = os.environ.get("TEST_PROVIDER")
    service_type = os.environ.get("TEST_SERVICE", "")
    method_name = os.environ.get("TEST_METHOD", "send")

    if not provider_name:
        pytest.skip("TEST_PROVIDER must be set")

    # Special case: check_package_and_config doesn't need a service type
    if method_name.lower() == "check_package_and_config":
        provider = instantiate_provider(provider_name)
        result = provider.check_package_and_config()

        assert isinstance(result, dict)
        assert "packages" in result
        assert "config" in result
        assert isinstance(result["packages"], dict)
        assert isinstance(result["config"], dict)
        return

    if not service_type:
        pytest.skip("TEST_SERVICE must be set")

    # Normalize service type
    service_to_missive = {
        "email": "EMAIL",
        "sms": "SMS",
        "postal": "POSTAL",
        "lre": "LRE",
        "push_notification": "PUSH_NOTIFICATION",
        "notification": "NOTIFICATION",
        "voice_call": "VOICE_CALL",
        "branded": "BRANDED",
    }
    missive_type = service_to_missive.get(service_type.lower(), service_type.upper())

    # Map method shortcuts to full method names
    method_map = {
        "send": f"send_{service_type}",
        "cancel": f"cancel_{service_type}",
        "check": f"check_{service_type}_delivery_status",
        "risk": f"calculate_{service_type}_delivery_risk",
        "info": f"get_{service_type}_service_info",
    }
    full_method_name = method_map.get(method_name.lower(), method_name)

    # Instantiate provider with default config
    provider = instantiate_provider(provider_name)

    # Create a basic missive based on service type
    missive_kwargs: Dict[str, Any] = {"missive_type": missive_type}
    if service_type == "email":
        missive_kwargs["recipient_email"] = "test@example.com"
    elif service_type == "sms":
        missive_kwargs["recipient_phone"] = "+33102030405"
    elif service_type == "push_notification":
        missive_kwargs["recipient"] = RecipientStub(
            metadata={"apn_device_token": "a" * 64}
        )
    elif service_type in ("postal", "lre"):
        missive_kwargs["recipient"] = RecipientStub(
            email="test@example.com",
            address_line1="123 Test St",
            postal_code="75001",
            city="Paris",
        )
    else:
        missive_kwargs["recipient"] = RecipientStub()

    missive = make_missive(**missive_kwargs)
    provider.missive = missive

    # Execute the method
    if not hasattr(provider, full_method_name):
        pytest.skip(f"Provider {provider_name} does not implement {full_method_name}")

    method = getattr(provider, full_method_name)
    result = method()

    # Basic assertions based on method type
    if method_name == "send":
        assert isinstance(result, bool)
        if result:
            assert missive.status == MissiveStatus.SENT
    elif method_name == "risk":
        assert isinstance(result, dict)
        assert "should_send" in result
        assert "risk_score" in result
    elif method_name == "check":
        assert isinstance(result, dict)
        assert "status" in result
    elif method_name == "info":
        assert isinstance(result, dict)
        assert "is_available" in result or "warnings" in result


# ---------------------------------------------------------------------------#
# Dispatch behaviour (existing generic tests)
# ---------------------------------------------------------------------------#


def test_check_delivery_status_dispatches_to_sms() -> None:
    provider = instantiate_provider("brevo", config={"BREVO_API_KEY": "token"})
    missive = make_missive(
        missive_type="SMS",
        recipient_phone="+33102030405",
    )
    provider.missive = missive

    def fake_check_sms_delivery_status(**kwargs):
        return {"status": "patched"}

    provider.check_sms_delivery_status = fake_check_sms_delivery_status  # type: ignore[assignment]
    result = provider.check_delivery_status()

    assert result["status"] == "patched"


def test_check_delivery_status_without_type_returns_unknown() -> None:
    provider = instantiate_provider("brevo", config={"BREVO_API_KEY": "token"})
    provider.missive = make_missive()

    result = provider.check_delivery_status()

    assert result["status"] == "unknown"
    assert "Missive type not defined" in result["error_message"]


def test_handle_webhook_dispatches_by_missive_type() -> None:
    provider = SMSWebhookProvider()
    success, message, data = provider.handle_webhook(
        {"message_id": "abc"}, {}, missive_type="sms"
    )

    assert success is True
    assert message == "handled"
    assert data == "abc"


def test_validate_webhook_signature_dispatches_by_missive_type() -> None:
    provider = SMSWebhookProvider()
    is_valid, error = provider.validate_webhook_signature({}, {}, missive_type="sms")

    assert is_valid is False
    assert error == "invalid signature"
