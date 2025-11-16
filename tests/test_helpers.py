"""Tests for provider discovery helpers."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import List

import pytest

from python_missive.helpers import (get_provider_paths_from_config,
                                    get_providers_from_config, load_providers)
from python_missive.providers import (BaseProviderCommon, ProviderImportError,
                                      build_registry,
                                      get_provider_name_from_path,
                                      load_provider_class)


@pytest.fixture
def module_factory():
    """Provide a helper that creates disposable provider modules."""
    created: List[str] = []

    def factory(
        module_name: str, provider_name: str, supported_types: List[str]
    ) -> str:
        module = ModuleType(module_name)
        DummyProvider = type(
            provider_name,
            (BaseProviderCommon,),
            {
                "name": provider_name,
                "supported_types": list(supported_types),
            },
        )
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
        get_provider_name_from_path("python_missive.providers.twilio.TwilioProvider")
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
