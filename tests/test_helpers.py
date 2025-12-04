"""Tests for provider discovery helpers."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any, Dict, List

import pytest

from pymissive.helpers import (format_phone_international,
                                    get_provider_paths_from_config,
                                    get_providers_for_type,
                                    get_providers_from_config, load_providers)
from pymissive.providers import (BaseProviderCommon, ProviderImportError,
                                      build_registry,
                                      get_provider_name_from_path,
                                      load_provider_class)


@pytest.fixture
def module_factory():
    """Provide a helper that creates disposable provider modules."""
    created: List[str] = []

    def factory(
        module_name: str,
        provider_name: str,
        supported_types: List[str],
        extra_attrs: Dict[str, Any] | None = None,
    ) -> str:
        module = ModuleType(module_name)
        attrs: Dict[str, Any] = {
            "name": provider_name,
            "supported_types": list(supported_types),
        }
        if extra_attrs:
            attrs.update(extra_attrs)
        DummyProvider = type(provider_name, (BaseProviderCommon,), attrs)
        setattr(module, provider_name, DummyProvider)
        sys.modules[module_name] = module
        created.append(module_name)
        return f"{module_name}.{provider_name}"

    yield factory

    for name in created:
        sys.modules.pop(name, None)


def test_load_provider_class_success(module_factory) -> None:
    import_path = module_factory("dummy_provider_module", "Dummy", ["EMAIL"])
    provider_class = load_provider_class(import_path)

    assert issubclass(provider_class, BaseProviderCommon)
    assert provider_class.name == "Dummy"


def test_load_provider_class_invalid_module() -> None:
    with pytest.raises(ProviderImportError):
        load_provider_class("nonexistent.module.Provider")


def test_load_provider_class_invalid_class() -> None:
    module_name = "module_without_class"
    module = ModuleType(module_name)
    sys.modules[module_name] = module

    with pytest.raises(ProviderImportError):
        load_provider_class(f"{module_name}.MissingClass")


def test_get_provider_name_from_path_variants() -> None:
    assert (
        get_provider_name_from_path("pymissive.providers.twilio.TwilioProvider")
        == "twilio"
    )
    assert get_provider_name_from_path("CustomProvider") == "customprovider"
    assert get_provider_name_from_path("") == "custom"


def test_get_providers_from_config_groups_by_type(module_factory) -> None:
    import_path_email = module_factory(
        "provider_one_module", "EmailProvider", ["EMAIL"]
    )
    import_path_sms = module_factory(
        "provider_two_module", "SmsProvider", ["SMS", "EMAIL"]
    )

    providers = get_providers_from_config([import_path_email, import_path_sms])

    assert providers == {
        "EMAIL": ["email", "sms"],
        "SMS": ["sms"],
    }


def test_get_provider_paths_from_config_returns_full_paths(module_factory) -> None:
    import_path_email = module_factory(
        "provider_three_module", "EmailProvider", ["EMAIL"]
    )
    import_path_sms = module_factory("provider_four_module", "SmsProvider", ["SMS"])

    providers = get_provider_paths_from_config([import_path_email, import_path_sms])

    assert providers == {
        "EMAIL": [import_path_email],
        "SMS": [import_path_sms],
    }


def test_load_providers_returns_short_and_full_mappings(module_factory) -> None:
    import_path_email = module_factory(
        "provider_five_module", "EmailProvider", ["EMAIL"]
    )
    import_path_sms = module_factory("provider_six_module", "SmsProvider", ["SMS"])

    short_names, full_paths = load_providers([import_path_email, import_path_sms])

    assert short_names == {
        "EMAIL": ["email"],
        "SMS": ["sms"],
    }
    assert full_paths == {
        "EMAIL": [import_path_email],
        "SMS": [import_path_sms],
    }


def test_build_registry_registers_and_groups(module_factory) -> None:
    import_path_email = module_factory(
        "provider_registry_email", "EmailProvider", ["EMAIL"]
    )
    import_path_sms = module_factory("provider_registry_sms", "SmsProvider", ["SMS"])

    registry = build_registry([import_path_email, import_path_sms])

    assert registry.group_by_type() == {
        "EMAIL": ["email"],
        "SMS": ["sms"],
    }

    grouped_paths = registry.group_paths_by_type()
    assert grouped_paths["EMAIL"][0].endswith("EmailProvider")
    assert grouped_paths["SMS"][0].endswith("SmsProvider")

    # Ensure instantiation returns a provider instance
    email_provider = registry.instantiate("email")
    assert isinstance(email_provider, BaseProviderCommon)


def test_build_registry_raises_when_provider_unknown() -> None:
    registry = build_registry([])

    with pytest.raises(ProviderImportError):
        registry.instantiate("missing")


def test_get_providers_for_type_supports_names_and_paths(module_factory) -> None:
    email_path = module_factory("provider_target_email", "EmailProvider", ["EMAIL"])
    sms_path = module_factory("provider_target_sms", "SmsProvider", ["SMS"])

    config = [email_path, sms_path]

    short_names = get_providers_for_type(config, "sms")
    full_paths = get_providers_for_type(config, "sms", use_paths=True)
    missing = get_providers_for_type(config, "unknown")

    assert short_names == ["sms"]
    assert full_paths == [sms_path]
    assert missing == []


def test_get_providers_for_type_ordering_by_class_attribute(module_factory) -> None:
    slow_path = module_factory(
        "provider_postal_slow",
        "PostalSlow",
        ["POSTAL"],
        extra_attrs={"max_postal_pages": 200},
    )
    fast_path = module_factory(
        "provider_postal_fast",
        "PostalFast",
        ["POSTAL"],
        extra_attrs={"max_postal_pages": 80},
    )

    providers = get_providers_for_type(
        [slow_path, fast_path],
        "POSTAL",
        ordering=["max_postal_pages"],
    )
    assert providers == ["postalfast", "postalslow"]

    reversed_providers = get_providers_for_type(
        [slow_path, fast_path],
        "POSTAL",
        ordering=["-max_postal_pages"],
    )
    assert reversed_providers == ["postalslow", "postalfast"]


def test_get_providers_for_type_ordering_by_config_metadata(module_factory) -> None:
    premium_path = module_factory(
        "provider_email_premium",
        "PremiumEmail",
        ["EMAIL"],
    )
    budget_path = module_factory(
        "provider_email_budget",
        "BudgetEmail",
        ["EMAIL"],
    )

    config = {
        premium_path: {"price": 0.15},
        budget_path: {"price": 0.05},
    }

    providers = get_providers_for_type(config, "EMAIL", ordering=["price"])
    assert providers == ["budgetemail", "premiumemail"]

    providers_desc = get_providers_for_type(config, "EMAIL", ordering=["-price"])
    assert providers_desc == ["premiumemail", "budgetemail"]

    overrides = {budget_path: {"price": 0.30}}
    providers_override = get_providers_for_type(
        config, "EMAIL", ordering=["price"], provider_metadata=overrides
    )
    assert providers_override == ["premiumemail", "budgetemail"]


def test_get_providers_for_type_multi_field_ordering(module_factory) -> None:
    cheap_fast = module_factory(
        "provider_multi_cheap_fast",
        "CheapFast",
        ["SMS"],
        extra_attrs={"priority": 2},
    )
    cheap_slow = module_factory(
        "provider_multi_cheap_slow",
        "CheapSlow",
        ["SMS"],
        extra_attrs={"priority": 5},
    )
    premium_fast = module_factory(
        "provider_multi_premium_fast",
        "PremiumFast",
        ["SMS"],
        extra_attrs={"priority": 1},
    )

    config = {
        cheap_fast: {"price": 0.05},
        cheap_slow: {"price": 0.05},
        premium_fast: {"price": 0.15},
    }

    providers = get_providers_for_type(
        config,
        "SMS",
        ordering=["price", "-priority"],
    )

    assert providers == ["cheapslow", "cheapfast", "premiumfast"]


def test_format_phone_international_french_numbers() -> None:
    """Test formatting French phone numbers."""
    assert format_phone_international("06 12 34 56 78") == "+33612345678"
    assert format_phone_international("0612345678") == "+33612345678"
    assert format_phone_international("07 12 34 56 78") == "+33712345678"
    assert format_phone_international("06-12-34-56-78") == "+33612345678"
    assert format_phone_international("06.12.34.56.78") == "+33612345678"
    assert format_phone_international("0612345678", "FR") == "+33612345678"


def test_format_phone_international_already_international() -> None:
    """Test formatting numbers already in international format."""
    assert format_phone_international("+33 6 12 34 56 78") == "+33612345678"
    assert format_phone_international("+33612345678") == "+33612345678"
    assert format_phone_international("+1 555 123 4567") == "+15551234567"
    assert format_phone_international("+44 20 7946 0958") == "+442079460958"
    # Format 00 (alternative international format)
    assert format_phone_international("0033 6 12 34 56 78") == "+33612345678"
    assert format_phone_international("0033612345678") == "+33612345678"
    assert format_phone_international("0044 20 7946 0958") == "+442079460958"


def test_format_phone_international_with_country_code() -> None:
    """Test formatting with explicit country code."""
    assert format_phone_international("0123456789", "FR") == "+33123456789"
    assert format_phone_international("0123456789", "GB") == "+44123456789"
    # US uses +1 as country code (not area codes from CSV)
    assert format_phone_international("0123456789", "US") == "+1123456789"


def test_format_phone_international_other_countries() -> None:
    """Test formatting numbers from other countries."""
    # US number (10 digits)
    assert format_phone_international("5551234567", "US") == "+15551234567"
    # UK number
    assert format_phone_international("2079460958", "GB") == "+442079460958"
    # German number
    assert format_phone_international("301234567", "DE") == "+49301234567"


def test_format_phone_international_edge_cases() -> None:
    """Test edge cases and invalid inputs."""
    # Empty string
    assert format_phone_international("") == ""
    # Whitespace only (should return empty after strip)
    assert format_phone_international("   ") == ""
    # Already formatted
    assert format_phone_international("+33612345678") == "+33612345678"
    # Number without leading 0 and no country code (assumes international without +)
    assert format_phone_international("33612345678") == "+33612345678"
