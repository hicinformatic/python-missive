"""Framework-agnostic helpers for provider discovery."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Sequence, Tuple

from .providers import (ProviderImportError, get_provider_name_from_path,
                        load_provider_class)

ErrorHandler = Callable[[str, Exception], None]


def _iter_provider_classes(
    provider_paths: Iterable[str],
    *,
    on_error: ErrorHandler | None = None,
):
    """Yield provider classes defined by the given import paths."""
    for provider_path in provider_paths:
        try:
            yield provider_path, load_provider_class(provider_path)
        except ProviderImportError as exc:
            if on_error:
                on_error(provider_path, exc)
            continue


def get_providers_from_config(
    providers_config: Sequence[str] | None,
    *,
    on_error: ErrorHandler | None = None,
) -> Dict[str, List[str]]:
    """Return providers grouped by missive type using short provider names."""
    if not providers_config:
        return {}

    providers_by_type: Dict[str, List[str]] = {}

    for provider_path, provider_class in _iter_provider_classes(
        providers_config, on_error=on_error
    ):
        provider_name = get_provider_name_from_path(provider_path)
        for missive_type in provider_class.supported_types:
            providers_by_type.setdefault(missive_type, [])
            if provider_name not in providers_by_type[missive_type]:
                providers_by_type[missive_type].append(provider_name)

    return providers_by_type


def get_provider_paths_from_config(
    providers_config: Sequence[str] | None,
    *,
    on_error: ErrorHandler | None = None,
) -> Dict[str, List[str]]:
    """Return providers grouped by missive type exposing full import paths."""
    if not providers_config:
        return {}

    providers_by_type: Dict[str, List[str]] = {}

    for provider_path, provider_class in _iter_provider_classes(
        providers_config, on_error=on_error
    ):
        for missive_type in provider_class.supported_types:
            providers_by_type.setdefault(missive_type, [])
            if provider_path not in providers_by_type[missive_type]:
                providers_by_type[missive_type].append(provider_path)

    return providers_by_type


def load_providers(
    providers_config: Sequence[str] | None,
    *,
    on_error: ErrorHandler | None = None,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Return both short-name and full-path provider mappings."""
    short_names = get_providers_from_config(providers_config, on_error=on_error)
    full_paths = get_provider_paths_from_config(providers_config, on_error=on_error)
    return short_names, full_paths
