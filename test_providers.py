#!/usr/bin/env python3
"""Test script to verify all providers can be imported and instantiated."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from python_missive.providers import (
    ProviderImportError,
    get_provider_name_from_path,
    load_provider_class,
)


class MockMissive:
    """Minimal mock missive object for testing."""
    
    def __init__(self):
        self.id = "test_123"
        self.missive_type = "EMAIL"
        self.recipient_email = "test@example.com"
        self.recipient_phone = "+33612345678"
        self.recipient_address = "123 Test Street\n75001 Paris"
        self.subject = "Test Subject"
        self.body = "Test body"
        self.body_text = "Test body"
        self.body_html = None
        self.status = None
        self.provider = None
        self.external_id = None
        self.error_message = None
        self.sent_at = None
        self.delivered_at = None
        self.read_at = None
        self.is_registered = False
        self.requires_signature = False
        
        # Mock recipient
        self.recipient = MockRecipient()
        self.recipient_user = None


class MockRecipient:
    """Minimal mock recipient object for testing."""
    
    def __init__(self):
        self.email = "test@example.com"
        self.mobile = "+33612345678"
        self.name = "Test User"
        self.address_line1 = "123 Test Street"
        self.postal_code = "75001"
        self.city = "Paris"
        self.metadata = {}


def _load_providers_config() -> Dict[str, Dict[str, Any]]:
    """Load MISSIVE_CONFIG_PROVIDERS from tests or local config."""
    import importlib

    for module_name in ("tests.test_config", "test_config"):
        try:
            module = importlib.import_module(module_name)
            config = getattr(module, "MISSIVE_CONFIG_PROVIDERS")
            if isinstance(config, dict):
                return config
        except (ImportError, AttributeError):
            continue
    raise ImportError(
        "MISSIVE_CONFIG_PROVIDERS not found. Ensure tests/test_config.py is accessible."
    )


def _build_missive_for_type(missive_type: str) -> MockMissive:
    """Return a minimal missive object compatible with the given type."""
    missive = MockMissive()
    normalized = missive_type.upper()
    missive.missive_type = normalized

    if normalized in {"NOTIFICATION"}:
        missive.recipient_user = MockRecipient()

    if normalized in {"PUSH_NOTIFICATION"}:
        missive.recipient.metadata["apn_device_token"] = "a" * 64

    if normalized in {
        "POSTAL",
        "POSTAL_REGISTERED",
        "POSTAL_SIGNATURE",
        "LRE",
        "LRE_QUALIFIED",
        "ERE",
    }:
        missive.recipient.address_line1 = "123 Test Street"
        missive.recipient.postal_code = "75001"
        missive.recipient.city = "Paris"
        missive.recipient.email = "test@example.com"

    if normalized in {"SMS", "VOICE_CALL", "BRANDED"}:
        missive.recipient_phone = "+33612345678"

    if normalized in {"EMAIL", "EMAIL_MARKETING", "ERE", "LRE"}:
        missive.recipient_email = "test@example.com"

    return missive


def _iter_supported_types(provider_class: type[BaseProvider]) -> Iterable[str]:
    types = getattr(provider_class, "supported_types", None)
    if not types:
        return ["EMAIL"]
    return [str(t).upper() for t in types]


def test_provider_import_and_instantiation():
    """Test that all providers can be imported and instantiated using config."""

    providers_config = _load_providers_config()
    results = []

    for provider_path, provider_settings in providers_config.items():
        provider_name = get_provider_name_from_path(provider_path)

        try:
            provider_class = load_provider_class(provider_path)
        except ProviderImportError as e:
            results.append((provider_name, False, f"Import error: {e}"))
            print(f"✗ {provider_name}: Import error - {e}")
            continue

        supported_types = list(_iter_supported_types(provider_class))
        config: Dict[str, Any] = (
            dict(provider_settings) if isinstance(provider_settings, dict) else {}
        )

        for missive_type in supported_types:
            label = f"{provider_name}[{missive_type}]"
            missive = _build_missive_for_type(missive_type)

            try:
                provider = provider_class(missive=missive, config=config)
            except Exception as exc:
                results.append((label, False, f"Instantiation failed: {exc}"))
                print(f"✗ {label}: Instantiation error - {exc}")
                break
            
            # Test basic attributes
            assert hasattr(provider, "name"), f"{provider_name} missing 'name' attribute"
            assert hasattr(provider, "supported_types"), f"{provider_name} missing 'supported_types' attribute"
            assert isinstance(provider.supported_types, list), f"{provider_name}.supported_types should be a list"
            
            # Test validate method
            try:
                is_valid, error = provider.validate()
                assert isinstance(is_valid, bool), f"{label}.validate() should return bool"
                assert isinstance(error, str), f"{label}.validate() should return str"
            except Exception as e:
                results.append((label, False, f"validate() failed: {e}"))
                print(f"✗ {label}: validate() error - {e}")
                break
            
            # Test get_service_status method
            try:
                status = provider.get_service_status()
                assert isinstance(status, dict), f"{label}.get_service_status() should return dict"
            except Exception as e:
                results.append((label, False, f"get_service_status() failed: {e}"))
                print(f"✗ {label}: get_service_status() error - {e}")
                break
            
            # Test supports method
            try:
                supports = provider.supports(missive_type)
                assert isinstance(supports, bool), f"{label}.supports() should return bool"
            except Exception as e:
                results.append((label, False, f"supports() failed: {e}"))
                print(f"✗ {label}: supports() error - {e}")
                break

            results.append((label, True, "OK"))
            print(f"✓ {label}: OK")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    failed = [(name, msg) for name, success, msg in results if not success]
    if failed:
        print("\nFailed providers:")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        return False
    
    return True


if __name__ == "__main__":
    success = test_provider_import_and_instantiation()
    exit(0 if success else 1)

