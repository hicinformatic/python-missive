#!/usr/bin/env python3
"""Test script to verify all providers can be imported and instantiated.

This script uses helpers to discover providers from configuration,
ensuring no hardcoded provider lists.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# Add src to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from python_missive.helpers import _iter_provider_classes
from python_missive.providers import get_provider_name_from_path, ProviderImportError


class MockMissive:
    """Minimal mock missive object for testing."""

    def __init__(self, missive_type: str = "EMAIL"):
        self.id = "test_123"
        self.missive_type = missive_type
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


def create_minimal_config(provider_class: Any) -> Dict[str, Any]:
    """Create minimal config for a provider based on its config_keys."""
    config: Dict[str, Any] = {}
    for key in provider_class.config_keys:
        # Set dummy values for testing
        if "API_KEY" in key or "TOKEN" in key or "SECRET" in key:
            config[key] = "test_key"
        elif "DOMAIN" in key:
            config[key] = "test.com"
        elif "EMAIL" in key:
            config[key] = "test@example.com"
        elif "PHONE" in key or "NUMBER" in key:
            config[key] = "+33612345678"
        elif "REGION" in key:
            config[key] = "eu-west-1"
        elif "ID" in key or "SID" in key:
            config[key] = "test_id"
        elif "URL" in key:
            config[key] = "https://test.com"
        else:
            config[key] = "test_value"
    return config


def test_provider(provider_path: str, provider_class: Any) -> tuple[bool, str]:
    """Test a single provider can be instantiated and basic methods work."""
    try:
        provider_name = get_provider_name_from_path(provider_path)

        # Determine appropriate missive type
        missive_type = provider_class.supported_types[0] if provider_class.supported_types else "EMAIL"
        missive = MockMissive(missive_type=missive_type)

        # Create minimal config
        config = create_minimal_config(provider_class)

        # Instantiate provider
        provider = provider_class(missive=missive, config=config)

        # Test basic attributes
        assert hasattr(provider, "name"), f"{provider_name} missing 'name' attribute"
        assert hasattr(provider, "supported_types"), f"{provider_name} missing 'supported_types' attribute"
        assert isinstance(provider.supported_types, list), f"{provider_name}.supported_types should be a list"

        # Test validate method
        is_valid, error = provider.validate()
        assert isinstance(is_valid, bool), f"{provider_name}.validate() should return bool"
        assert isinstance(error, str), f"{provider_name}.validate() should return str"

        # Test get_service_status method
        status = provider.get_service_status()
        assert isinstance(status, dict), f"{provider_name}.get_service_status() should return dict"

        # Test supports method
        supports = provider.supports(missive_type)
        assert isinstance(supports, bool), f"{provider_name}.supports() should return bool"

        return True, "OK"

    except AssertionError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Error: {e}"


def main() -> int:
    """Main test function."""
    # Load providers config from command line or default
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_providers_import.py <module_path>")
        print("Example: python scripts/test_providers_import.py tests.test_config.MISSIVE_CONFIG_PROVIDERS")
        return 1

    module_path = sys.argv[1]

    # Load configuration using dev.py helper
    try:
        # Import dev.py helper
        sys.path.insert(0, str(PROJECT_ROOT))
        from dev import load_module_attribute

        MISSIVE_CONFIG_PROVIDERS = load_module_attribute(module_path)
        providers_config_dict = MISSIVE_CONFIG_PROVIDERS
        providers_config = (
            list(MISSIVE_CONFIG_PROVIDERS.keys())
            if isinstance(MISSIVE_CONFIG_PROVIDERS, dict)
            else MISSIVE_CONFIG_PROVIDERS
        )
    except Exception as e:
        print(f"ERROR: Could not load configuration from {module_path}: {e}")
        return 1

    if not providers_config:
        print("ERROR: No providers found in configuration.")
        return 1

    print("=" * 80)
    print("TESTING PROVIDERS IMPORT AND INSTANTIATION")
    print("=" * 80)
    print(f"Configuration: {module_path}")
    print(f"Providers found: {len(providers_config)}")
    print()

    results = []
    errors = []

    def on_error(provider_path: str, exc: Exception) -> None:
        """Handle provider import errors."""
        provider_name = get_provider_name_from_path(provider_path)
        errors.append((provider_name, f"Import error: {exc}"))
        print(f"✗ {provider_name}: Import error - {exc}")

    # Test all providers
    for provider_path, provider_class in _iter_provider_classes(
        providers_config, on_error=on_error
    ):
        provider_name = get_provider_name_from_path(provider_path)
        success, message = test_provider(provider_path, provider_class)
        results.append((provider_name, success, message))
        if success:
            print(f"✓ {provider_name}: {message}")
        else:
            print(f"✗ {provider_name}: {message}")

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    passed = sum(1 for _, success, _ in results if success)
    total = len(results) + len(errors)
    print(f"Passed: {passed}/{total}")

    failed = [(name, msg) for name, success, msg in results if not success]
    if failed:
        print("\nFailed providers:")
        for name, msg in failed:
            print(f"  - {name}: {msg}")

    if errors:
        print("\nImport errors:")
        for name, msg in errors:
            print(f"  - {name}: {msg}")

    if failed or errors:
        return 1

    print("\n✓ All providers passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

