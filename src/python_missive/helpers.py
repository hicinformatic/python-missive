"""Framework-agnostic helpers for provider discovery."""

from __future__ import annotations

import csv
import os
import re
from functools import cmp_to_key
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    cast,
)

try:
    from .address_backends import BaseAddressBackend
except ImportError:
    BaseAddressBackend = None  # type: ignore[assignment, misc]

from .providers import (
    BaseProviderCommon,
    ProviderImportError,
    get_provider_name_from_path,
    load_provider_class,
)

ErrorHandler = Callable[[str, Exception], None]
_ProvidersConfig = Sequence[str] | Mapping[str, Mapping[str, Any]]

# Cache for country phone codes
_COUNTRY_PHONE_CODES: Dict[str, List[str]] = {}

try:
    _DEFAULT_MIN_CONFIDENCE = float(os.getenv("PYTHON_MISSIVE_MIN_ADDRESS_CONFIDENCE", "0.4"))
except ValueError:
    _DEFAULT_MIN_CONFIDENCE = 0.4

DEFAULT_MIN_ADDRESS_CONFIDENCE = max(0.0, _DEFAULT_MIN_CONFIDENCE)


def _load_country_phone_codes() -> Dict[str, List[str]]:
    """Load country phone codes from countries.csv with caching."""
    if _COUNTRY_PHONE_CODES:
        return _COUNTRY_PHONE_CODES

    csv_path = Path(__file__).parent.parent.parent / "data" / "countries.csv"
    if not csv_path.exists():
        return {}

    loaded_codes: Dict[str, List[str]] = {}
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                country_code = row.get("cca2", "").upper()
                phone_codes_str = row.get("phone_codes", "").strip()
                if country_code and phone_codes_str:
                    # Handle multiple codes separated by semicolons
                    codes = [
                        code.strip().lstrip("+")
                        for code in phone_codes_str.split(";")
                        if code.strip()
                    ]
                    if codes:
                        loaded_codes[country_code] = codes
    except Exception:
        pass

    # Update global cache
    _COUNTRY_PHONE_CODES.update(loaded_codes)
    return _COUNTRY_PHONE_CODES


def format_phone_international(phone: str, country_code: Optional[str] = None) -> str:
    """Format a phone number in international E.164 format.

    Handles various input formats:
    - French numbers: "06 12 34 56 78" -> "+33612345678"
    - Numbers with country code: "+33 6 12 34 56 78" -> "+33612345678"
    - International format: "+33612345678" -> "+33612345678" (unchanged)
    - Other countries: "0123456789" with country_code="US" -> "+10123456789"

    Args:
        phone: Phone number in any format (may include spaces, dashes, etc.)
        country_code: Optional ISO 3166-1 alpha-2 country code (e.g., "FR", "US", "GB").
            If not provided and number doesn't start with +, defaults to "FR" for numbers
            starting with 0.

    Returns:
        Phone number in E.164 format (e.g., "+33612345678").

    Examples:
        >>> format_phone_international("06 12 34 56 78")
        '+33612345678'
        >>> format_phone_international("+33 6 12 34 56 78")
        '+33612345678'
        >>> format_phone_international("0612345678", "FR")
        '+33612345678'
        >>> format_phone_international("+1 555 123 4567")
        '+15551234567'
    """
    if not phone or not isinstance(phone, str):
        return phone

    # Strip whitespace first
    phone = phone.strip()
    if not phone:
        return ""

    # Remove all non-digit characters except +
    cleaned = re.sub(r"[^\d+]", "", phone)

    if not cleaned:
        return phone

    # Handle 00 prefix (international format alternative to +)
    # Convert 00 to + for easier processing
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    # If already in international format, return cleaned
    if cleaned.startswith("+"):
        return cleaned

    # Special handling for US/Canada: use +1 as primary code
    # (CSV contains area codes, but we want the country code)
    _US_CANADA_CODES = {"US": "1", "CA": "1"}

    # If number starts with 0, it's likely a national format
    if cleaned.startswith("0"):
        # Default to France if no country_code provided
        if not country_code:
            country_code = "FR"

        country_code_upper = country_code.upper()

        # Special case for US/Canada
        if country_code_upper in _US_CANADA_CODES:
            return f"+{_US_CANADA_CODES[country_code_upper]}{cleaned[1:]}"

        # Load country phone codes
        country_codes = _load_country_phone_codes()
        phone_code = country_codes.get(country_code_upper)

        if phone_code:
            # For countries with multiple codes, use the shortest one (usually the main code)
            # Remove leading 0 and add country code
            main_code = min(phone_code, key=len)
            return f"+{main_code}{cleaned[1:]}"

        # Fallback: if country_code is FR, use +33
        if country_code_upper == "FR":
            return f"+33{cleaned[1:]}"

    # If country_code is provided and number doesn't start with 0
    if country_code:
        country_code_upper = country_code.upper()

        # Special case for US/Canada
        if country_code_upper in _US_CANADA_CODES:
            return f"+{_US_CANADA_CODES[country_code_upper]}{cleaned}"

        country_codes = _load_country_phone_codes()
        phone_code = country_codes.get(country_code_upper)
        if phone_code:
            # Use the shortest code (main country code)
            main_code = min(phone_code, key=len)
            return f"+{main_code}{cleaned}"

    # If no country_code and number doesn't start with 0, assume it's already
    # in international format without the +, or return as-is with +
    return f"+{cleaned}"


def _is_safe_attribute_name(name: str) -> bool:
    """Validate that an attribute name is safe to access via getattr.

    Prevents access to private/magic attributes and ensures the name
    is a valid Python identifier.
    """
    if not name or not isinstance(name, str):
        return False
    # Block access to private/magic attributes (starting with __)
    if name.startswith("__") and name.endswith("__"):
        return False
    # Block access to private attributes (starting with _)
    if name.startswith("_"):
        return False
    # Ensure it's a valid Python identifier
    return name.isidentifier()


# Map missive types to their config_fields prefix
_TYPE_PREFIX_MAP: Dict[str, str] = {}


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


def _split_providers_config(
    providers_config: _ProvidersConfig | None,
) -> Tuple[List[str], Dict[str, Mapping[str, Any]]]:
    """Return provider path list plus inline metadata (if mapping provided)."""
    if not providers_config:
        return [], {}

    if isinstance(providers_config, Mapping):
        return list(providers_config.keys()), dict(providers_config)

    return list(providers_config), {}


def _group_providers_by_type(
    providers_config: Sequence[str] | None,
    *,
    use_paths: bool = False,
    on_error: ErrorHandler | None = None,
) -> Dict[str, List[str]]:
    """Group providers by missive type, returning either paths or short names."""
    if not providers_config:
        return {}

    providers_by_type: Dict[str, List[str]] = {}

    for provider_path, provider_class in _iter_provider_classes(
        providers_config, on_error=on_error
    ):
        identifier = provider_path if use_paths else get_provider_name_from_path(provider_path)
        for missive_type in provider_class.supported_types:
            providers_by_type.setdefault(missive_type, [])
            if identifier not in providers_by_type[missive_type]:
                providers_by_type[missive_type].append(identifier)

    return providers_by_type


def get_providers_from_config(
    providers_config: Sequence[str] | None,
    *,
    on_error: ErrorHandler | None = None,
) -> Dict[str, List[str]]:
    """Return providers grouped by missive type using short provider names."""
    return _group_providers_by_type(providers_config, use_paths=False, on_error=on_error)


def get_provider_paths_from_config(
    providers_config: Sequence[str] | None,
    *,
    on_error: ErrorHandler | None = None,
) -> Dict[str, List[str]]:
    """Return providers grouped by missive type exposing full import paths."""
    return _group_providers_by_type(providers_config, use_paths=True, on_error=on_error)


def load_providers(
    providers_config: Sequence[str] | None,
    *,
    on_error: ErrorHandler | None = None,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Return both short-name and full-path provider mappings."""
    short_names = get_providers_from_config(providers_config, on_error=on_error)
    full_paths = get_provider_paths_from_config(providers_config, on_error=on_error)
    return short_names, full_paths


def _derive_config_fields_attr(target_type: str) -> str:
    normalized = target_type.strip().lower().replace(" ", "_")
    return f"{normalized}_config_fields"


def _get_valid_order_fields(
    provider_paths: Sequence[str], target_type: str, config_fields_attr: str
) -> set[str]:
    """Get valid ordering fields from *_config_fields of providers."""
    valid_order_fields: set[str] = set()
    # Security: config_fields_attr is constructed from a safe prefix (EMAIL, SMS, POSTAL, etc.)
    # and always ends with "_config_fields", so it's safe to use with getattr
    if not _is_safe_attribute_name(config_fields_attr):
        return valid_order_fields
    # Try to load at least one provider to get config_fields structure
    for provider_path in provider_paths:
        try:
            provider_class = load_provider_class(provider_path)
            if target_type not in getattr(provider_class, "supported_types", []):
                continue
            config_fields = getattr(provider_class, config_fields_attr, None)
            if isinstance(config_fields, list):
                valid_order_fields.update(config_fields)
                break  # We only need one provider to know the structure
        except ProviderImportError:
            continue
    return valid_order_fields


def _parse_ordering_fields(
    ordering: Sequence[str], valid_order_fields: set[str]
) -> List[Tuple[str, bool]]:
    """Parse and validate ordering fields, returning list of (field, ascending) tuples."""
    order_specs: List[Tuple[str, bool]] = []
    for field in ordering:
        if not field:
            continue
        ascending = True
        clean_field = field
        if field.startswith("-"):
            ascending = False
            clean_field = field[1:]
        if not clean_field:
            continue

        # Security: Validate field name is safe
        if not _is_safe_attribute_name(clean_field):
            continue

        # Only add if field is in valid_order_fields (from *_config_fields)
        # If valid_order_fields is empty, accept all fields (fallback)
        if not valid_order_fields or clean_field in valid_order_fields:
            order_specs.append((clean_field, ascending))
    return order_specs


def _build_provider_entries(
    provider_paths: Sequence[str],
    target_type: str,
    base_index: Dict[str, int],
    combined_metadata: Dict[str, Mapping[str, Any]],
    use_paths: bool,
    on_error: ErrorHandler | None = None,
) -> List[Tuple[str, str, Any, Mapping[str, Any]]]:
    """Build list of provider entries for sorting."""
    entries: List[Tuple[str, str, Any, Mapping[str, Any]]] = []

    for provider_path, provider_class in _iter_provider_classes(provider_paths, on_error=on_error):
        if target_type not in getattr(provider_class, "supported_types", []):
            continue

        identifier = provider_path if use_paths else get_provider_name_from_path(provider_path)
        if identifier not in base_index:
            continue

        metadata = combined_metadata.get(provider_path, {})
        entries.append((identifier, provider_path, provider_class, metadata))

    return entries


def get_providers_for_type(
    providers_config: _ProvidersConfig | None,
    missive_type: str,
    *,
    use_paths: bool = False,
    ordering: Sequence[str] | None = None,
    provider_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    on_error: ErrorHandler | None = None,
) -> List[str]:
    """Return providers for a single missive type (short names or import paths).

    Args:
        providers_config: Iterable (or mapping) of provider import paths.
            If a mapping is provided, its values are treated as provider-specific
            metadata useful for ordering.
        missive_type: Target missive type (EMAIL, SMS, POSTAL, etc.).
        use_paths: When True, return import paths instead of short provider names.
        ordering: Optional attribute/config names used to sort providers.
            Prefix a field with '-' for descending order (e.g., ['-email_price']).
        provider_metadata: Extra metadata keyed by provider import path which
            overrides inline metadata coming from the mapping form of
            `providers_config`.
        on_error: Optional callback for provider import failures.
    """
    if not missive_type:
        return []

    provider_paths, inline_metadata = _split_providers_config(providers_config)
    loader_input: Sequence[str] | None = provider_paths if provider_paths else None
    loader = get_provider_paths_from_config if use_paths else get_providers_from_config
    providers_by_type = loader(loader_input, on_error=on_error)
    base_list = list(providers_by_type.get(missive_type.upper(), []))

    # If no ordering requested, return base list
    if not ordering or not base_list:
        return base_list

    target_type = missive_type.upper()
    config_fields_attr = _derive_config_fields_attr(target_type)

    # Get valid ordering fields from *_config_fields
    valid_order_fields = _get_valid_order_fields(provider_paths, target_type, config_fields_attr)

    # Parse and validate ordering fields
    order_specs = _parse_ordering_fields(ordering, valid_order_fields)

    # If no valid ordering fields, return base list
    if not order_specs:
        return base_list

    combined_metadata: Dict[str, Mapping[str, Any]] = {}
    combined_metadata.update(inline_metadata)
    if provider_metadata:
        combined_metadata.update(provider_metadata)

    base_index = {identifier: idx for idx, identifier in enumerate(base_list)}
    entries = _build_provider_entries(
        provider_paths, target_type, base_index, combined_metadata, use_paths, on_error
    )

    def _extract_value(metadata: Mapping[str, Any], field: str, provider_class: Any) -> Any:
        """Extract value from metadata or provider class attribute.

        Fields are already validated to be in *_config_fields and safe to access.
        """
        # Security: Double-check field name is safe before accessing
        if not _is_safe_attribute_name(field):
            return None

        # First check metadata (overrides class attributes)
        if field in metadata:
            return metadata[field]

        # Try direct attribute access (field is already validated to exist and be safe)
        return getattr(provider_class, field, None)

    def _compare_entries(
        a: Tuple[str, str, Any, Mapping[str, Any]],
        b: Tuple[str, str, Any, Mapping[str, Any]],
    ) -> int:
        a_identifier, _, a_class, a_metadata = a
        b_identifier, _, b_class, b_metadata = b

        for field, ascending in order_specs:
            a_value = _extract_value(a_metadata, field, a_class)
            b_value = _extract_value(b_metadata, field, b_class)

            if a_value is None and b_value is None:
                continue
            if a_value is None:
                return 1
            if b_value is None:
                return -1

            if a_value < b_value:
                return -1 if ascending else 1
            if a_value > b_value:
                return 1 if ascending else -1

        a_fallback = base_index.get(a_identifier, float("inf"))
        b_fallback = base_index.get(b_identifier, float("inf"))
        if a_fallback == b_fallback:
            return 0
        return -1 if a_fallback < b_fallback else 1

    entries.sort(key=cmp_to_key(_compare_entries))
    return [identifier for identifier, _, _, _ in entries]


def _load_address_backend_class(backend_path: str) -> Type[BaseAddressBackend]:
    """Load an address backend class from its import path."""
    if BaseAddressBackend is None:
        raise ImportError("address_backends module not available")

    import importlib

    parts = backend_path.split(".")
    module_path = ".".join(parts[:-1])
    class_name = parts[-1]

    # Security: class_name comes from a trusted configuration path
    # and is validated to be a safe attribute name
    if not _is_safe_attribute_name(class_name):
        raise ValueError(f"Invalid class name in backend path: {backend_path}")

    module = importlib.import_module(module_path)
    backend_class = getattr(module, class_name)
    return cast(Type[BaseAddressBackend], backend_class)


def _filter_backend_configs_by_name(
    backends_config: Sequence[Dict[str, Any]], backend_names: str | List[str]
) -> List[Dict[str, Any]]:
    """Filter backend configs to only include those matching the backend name(s).

    Args:
        backends_config: List of backend configurations.
        backend_names: Name(s) of the backend(s) to filter (e.g., "nominatim",
            ["nominatim", "google_maps"]).

    Returns:
        List containing only the matching backend configs, or empty list if none found.
    """
    # Normalize to list
    if isinstance(backend_names, str):
        backend_names_list = [backend_names]
    else:
        backend_names_list = backend_names

    # Normalize names to lowercase for comparison
    backend_names_lower = [name.lower().strip() for name in backend_names_list if name]
    if not backend_names_lower:
        return []

    filtered_configs: List[Dict[str, Any]] = []

    for backend_config in backends_config:
        try:
            backend_class = _load_address_backend_class(backend_config["class"])
            backend_name = getattr(backend_class, "name", "").lower()
            # Check if the backend class name matches any of the requested names
            if backend_name in backend_names_lower:
                filtered_configs.append(backend_config)
                # If we've found all requested backends, we can stop early
                if len(filtered_configs) >= len(backend_names_lower):
                    break
        except (ImportError, AttributeError, ValueError):
            # Skip invalid backends
            continue

    return filtered_configs


def get_address_backends_from_config(
    backends_config: Sequence[Dict[str, Any]] | None = None,
) -> List[BaseAddressBackend]:
    """Load address backends from configuration.

    Args:
        backends_config: List of backend configurations, each with:
            - "class": Import path to backend class
            - "config": Configuration dict for the backend
            If None, returns empty list.

    Returns:
        List of instantiated backend instances that are properly configured.

    Example:
        >>> config = [
        ...     {
        ...         "class": "python_missive.address_backends.nominatim.NominatimAddressBackend",
        ...         "config": {"NOMINATIM_USER_AGENT": "my-app/1.0"},
        ...     }
        ... ]
        >>> backends = get_address_backends_from_config(config)
        >>> len(backends)
        1
    """
    if not backends_config:
        return []

    backends: List[BaseAddressBackend] = []

    for backend_config in backends_config:
        try:
            backend_class = _load_address_backend_class(backend_config["class"])
            config = backend_config.get("config", {})

            backend = backend_class(config=config)
            check = backend.check_package_and_config()

            # Check if required packages are installed
            packages = check.get("packages", {})
            if any(status == "missing" for status in packages.values()):
                continue

            # Check if required config keys are present (for paid backends)
            config_status = check.get("config", {})
            required_keys = backend_class.config_keys
            if required_keys:
                # For backends with required keys, check if ALL are configured and non-empty
                has_config = all(
                    config_status.get(key) == "present" and config.get(key) for key in required_keys
                )
                if not has_config:
                    # Skip if required config is missing or empty
                    continue

            backends.append(backend)

        except (ImportError, AttributeError, ValueError):
            # Backend class not found or invalid, skip
            continue

    return backends


_DEFAULT_ADDRESS_KWARGS: Dict[str, Optional[str]] = {
    "address_line1": "123 Test St",
    "address_line2": None,
    "address_line3": None,
    "city": "Paris",
    "postal_code": "75001",
    "state": None,
    "country": "FR",
}

_DEFAULT_EXTRA_KWARGS: Dict[str, Optional[float]] = {
    "latitude": 48.8566,
    "longitude": 2.3522,
}


def _resolve_address_kwargs(
    address_kwargs: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    resolved = _DEFAULT_ADDRESS_KWARGS.copy()
    if not address_kwargs:
        return resolved

    for key, value in address_kwargs.items():
        if value is None or value == "":
            continue
        resolved[key] = str(value)
    return resolved


def _resolve_extra_kwargs(
    operation: str, extra_kwargs: Optional[Dict[str, Any]]
) -> Dict[str, Optional[float]]:
    resolved = _DEFAULT_EXTRA_KWARGS.copy()
    if operation != "reverse_geocode" or not extra_kwargs:
        return resolved

    try:
        if "latitude" in extra_kwargs and extra_kwargs["latitude"] is not None:
            resolved["latitude"] = float(extra_kwargs["latitude"])
        if "longitude" in extra_kwargs and extra_kwargs["longitude"] is not None:
            resolved["longitude"] = float(extra_kwargs["longitude"])
    except (TypeError, ValueError):
        pass

    return resolved


def _coerce_confidence(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _passes_min_confidence(value: Any, threshold: float) -> bool:
    confidence = _coerce_confidence(value)
    if confidence is None:
        return True
    return confidence >= threshold


def _resolve_min_confidence(min_confidence: Optional[float]) -> float:
    if min_confidence is None:
        return DEFAULT_MIN_ADDRESS_CONFIDENCE
    try:
        threshold = float(min_confidence)
    except (TypeError, ValueError):
        return DEFAULT_MIN_ADDRESS_CONFIDENCE
    return max(0.0, threshold)


def _mask_value(value: Any) -> Optional[str]:
    if not value:
        return None
    value_str = str(value)
    if len(value_str) <= 6:
        return value_str
    return f"{value_str[:3]}…{value_str[-2:]}"


def _build_backend_diagnostic(  # noqa: C901
    backend_config: Dict[str, Any],
    working_instances: Dict[str, BaseAddressBackend],
    selected_backend: Optional[str],
) -> Dict[str, Any]:
    class_path = backend_config.get("class", "")
    config = backend_config.get("config", {}) or {}
    class_name = class_path.split(".")[-1] if class_path else "UnknownBackend"
    data: Dict[str, Any] = {
        "class": class_path,
        "class_name": class_name,
        "status": "error",
        "backend_name": None,
        "documentation_url": None,
        "site_url": None,
        "required_packages": [],
        "required_config_keys": [],
        "packages": {},
        "config": {},
        "selected": False,
        "error": None,
    }

    try:
        backend_class = _load_address_backend_class(class_path)

        # Extract class-level info first (before instantiation, in case it fails)
        class_backend_name = getattr(backend_class, "name", None)
        class_display_name = getattr(backend_class, "display_name", None)
        class_documentation_url = getattr(backend_class, "documentation_url", None)
        class_site_url = getattr(backend_class, "site_url", None)
        class_required_packages = getattr(backend_class, "required_packages", [])
        class_config_keys = getattr(backend_class, "config_keys", [])

        class_label = None
        if class_display_name:
            class_label = class_display_name
        elif class_backend_name:
            class_label = class_backend_name.replace("_", " ").title()

        # Update with class-level info as fallback
        if class_backend_name and not data.get("backend_name"):
            data["backend_name"] = class_backend_name
        if class_label and not data.get("backend_display_name"):
            data["backend_display_name"] = class_label
        if class_documentation_url and not data.get("documentation_url"):
            data["documentation_url"] = class_documentation_url
        if class_site_url and not data.get("site_url"):
            data["site_url"] = class_site_url
        if class_required_packages and not data.get("required_packages"):
            data["required_packages"] = class_required_packages
        if class_config_keys and not data.get("required_config_keys"):
            data["required_config_keys"] = class_config_keys

        backend_instance = working_instances.get(class_name) or backend_class(config=config)
        check = backend_instance.check_package_and_config()
        packages = check.get("packages", {})
        config_status = check.get("config", {})
        missing_packages = [pkg for pkg, status in packages.items() if status != "installed"]
        missing_config = [
            key
            for key in backend_instance.config_keys
            if config_status.get(key) != "present" or not config.get(key)
        ]
        is_working = class_name in working_instances

        if is_working:
            status = "working"
        elif missing_packages:
            status = "missing_packages"
        elif missing_config:
            status = "missing_config"
        else:
            status = "unavailable"

        data.update(
            {
                "status": status,
                "backend_name": getattr(backend_instance, "name", class_name),
                "backend_display_name": getattr(
                    backend_instance,
                    "label",
                    getattr(backend_instance, "name", class_name),
                ),
                "documentation_url": backend_instance.documentation_url,
                "site_url": backend_instance.site_url,
                "required_packages": backend_instance.required_packages,
                "required_config_keys": backend_instance.config_keys,
                "packages": packages,
                "config": {
                    key: {
                        "present": config_status.get(key) == "present",
                        "value_preview": _mask_value(config.get(key)),
                    }
                    for key in (backend_instance.config_keys or config.keys())
                },
                "selected": selected_backend == getattr(backend_instance, "name", None),
            }
        )
    except Exception as exc:
        error_msg = str(exc)
        data["error"] = error_msg

        # Even if instantiation failed, try to get info from the class itself
        try:
            backend_class = _load_address_backend_class(class_path)

            # Extract all class-level attributes at once
            if not data.get("backend_name"):
                data["backend_name"] = getattr(backend_class, "name", None)
            if not data.get("backend_display_name"):
                class_display_name = getattr(backend_class, "display_name", None)
                class_backend_name = data.get("backend_name") or getattr(
                    backend_class, "name", None
                )
                if class_display_name:
                    data["backend_display_name"] = class_display_name
                elif class_backend_name:
                    data["backend_display_name"] = class_backend_name.replace("_", " ").title()

            # Extract other class-level attributes even if instantiation failed
            if not data.get("documentation_url"):
                data["documentation_url"] = getattr(backend_class, "documentation_url", None)
            if not data.get("site_url"):
                data["site_url"] = getattr(backend_class, "site_url", None)
            if not data.get("required_packages"):
                data["required_packages"] = getattr(backend_class, "required_packages", [])
            if not data.get("required_config_keys"):
                data["required_config_keys"] = getattr(backend_class, "config_keys", [])

            # If the error is about missing config, try to determine the correct status
            # Check if error mentions required config or API key
            error_lower = error_msg.lower()
            is_config_error = any(
                keyword in error_lower
                for keyword in ["required", "missing", "api key", "config", "not provided"]
            )

            if is_config_error:
                # Try to check packages and config separately
                try:
                    # Create a temporary instance with empty config to check packages
                    # Some backends might allow this, others might not
                    from importlib import import_module

                    # Check packages
                    required_packages = getattr(backend_class, "required_packages", [])
                    packages = {}
                    missing_packages = []

                    for pkg in required_packages:
                        try:
                            import_module(pkg)
                            packages[pkg] = "installed"
                        except ImportError:
                            packages[pkg] = "missing"
                            missing_packages.append(pkg)

                    # Check config
                    config_keys = getattr(backend_class, "config_keys", [])
                    config_status = {}
                    missing_config = []

                    for key in config_keys:
                        if config.get(key):
                            config_status[key] = "present"
                        else:
                            config_status[key] = "missing"
                            missing_config.append(key)

                    # Determine status based on what's missing
                    if missing_packages:
                        data["status"] = "missing_packages"
                    elif missing_config:
                        data["status"] = "missing_config"
                    else:
                        data["status"] = "error"

                    # Update packages and config info
                    data["packages"] = packages
                    data["config"] = {
                        key: {
                            "present": config_status.get(key) == "present",
                            "value_preview": _mask_value(config.get(key)),
                        }
                        for key in config_keys
                    }
                except Exception:
                    # If we can't determine status, keep it as "error"
                    pass
        except Exception:
            pass  # If class loading also fails, keep None values

    return data


def describe_address_backends(
    backends_config: Sequence[Dict[str, Any]] | None,
    *,
    operation: str = "validate",
    address_kwargs: Optional[Dict[str, Any]] = None,
    extra_kwargs: Optional[Dict[str, Any]] = None,
    skip_api_test: bool = False,
) -> Dict[str, Any]:
    """Describe the status of configured address verification backends.

    Args:
        backends_config: List of backend configurations.
        operation: Operation to test ("validate", "geocode", "reverse_geocode").
        address_kwargs: Address parameters for testing.
        extra_kwargs: Extra parameters (e.g., latitude/longitude for reverse_geocode).
        skip_api_test: If True, skip the actual API call test (faster, no network).
    """
    if not backends_config:
        return {
            "configured": 0,
            "working": 0,
            "selected_backend": None,
            "sample_operation": "validate",
            "sample_result": {"error": "No address backends configured"},
            "items": [],
            "address_kwargs": _DEFAULT_ADDRESS_KWARGS.copy(),
            "extra_kwargs": _DEFAULT_EXTRA_KWARGS.copy(),
            "operations": ["validate", "geocode", "reverse_geocode"],
        }

    allowed_operations = {"validate", "geocode", "reverse_geocode"}
    normalized_operation = (operation or "validate").lower()
    if normalized_operation not in allowed_operations:
        normalized_operation = "validate"

    resolved_address_kwargs = _resolve_address_kwargs(address_kwargs)
    resolved_extra_kwargs = (
        _resolve_extra_kwargs(normalized_operation, extra_kwargs)
        if normalized_operation == "reverse_geocode"
        else {}
    )
    extra_kwargs_for_call: Dict[str, Any] = (
        dict(resolved_extra_kwargs) if normalized_operation == "reverse_geocode" else {}
    )

    # Skip API test if requested (for faster queryset construction)
    sample_result: Dict[str, Any] = {"error": "API test skipped", "backend_used": None}
    selected_backend: Optional[str] = None

    if not skip_api_test:
        backends = get_address_backends_from_config(backends_config)

        if normalized_operation == "reverse_geocode":
            # Handle reverse_geocode separately
            lat = extra_kwargs_for_call.get("latitude")
            lon = extra_kwargs_for_call.get("longitude")
            if lat is not None and lon is not None:
                for backend in backends:
                    try:
                        result = backend.reverse_geocode(lat, lon, **extra_kwargs_for_call)
                        if not result.get("error"):
                            result["backend_used"] = backend.name
                            sample_result = result
                            selected_backend = backend.name
                            break
                    except Exception:
                        continue
            if not sample_result:
                sample_result = {
                    "error": "Reverse geocode failed",
                    "backend_used": None,
                }
        else:
            # Use search_addresses for validate/geocode
            address_parts = [
                resolved_address_kwargs.get("address_line1"),
                resolved_address_kwargs.get("postal_code"),
                resolved_address_kwargs.get("city"),
            ]
            test_query = ", ".join(filter(None, address_parts)) or "test address"
            search_result = search_addresses(
                backends_config=backends_config,
                query=test_query,
                country=resolved_address_kwargs.get("country"),
                min_confidence=None,
                limit=1,
            )
            results = search_result.get("results", [])
            if results:
                sample_result = results[0]
                sample_result["backend_used"] = search_result.get("backend_used")
            else:
                sample_result = search_result
            selected_backend = sample_result.get("backend_used")

    working_instances_list = get_address_backends_from_config(backends_config)
    working_instances = {
        instance.__class__.__name__: instance for instance in working_instances_list
    }

    items = [
        _build_backend_diagnostic(config, working_instances, selected_backend)
        for config in backends_config
    ]

    return {
        "configured": len(backends_config),
        "working": len(working_instances),
        "selected_backend": selected_backend,
        "sample_operation": normalized_operation,
        "sample_result": sample_result,
        "items": items,
        "address_kwargs": resolved_address_kwargs,
        "extra_kwargs": resolved_extra_kwargs,
        "operations": ["validate", "geocode", "reverse_geocode"],
    }


def get_provider_by_attribute(
    providers_config: _ProvidersConfig | None,
    attribute: str,
    value: str,
    *,
    on_error: ErrorHandler | None = None,
) -> Optional[Type[BaseProviderCommon]]:
    """Get a provider class by matching an attribute value.

    Args:
        providers_config: Iterable (or mapping) of provider import paths.
        attribute: Attribute name to search (e.g., "name", "display_name").
        value: Value to match (case-insensitive).
        on_error: Optional callback for provider import failures.

    Returns:
        Provider class if found, None otherwise.

    Example:
        >>> config = ["python_missive.providers.brevo.BrevoProvider"]
        >>> provider_class = get_provider_by_attribute(config, "name", "Brevo")
        >>> provider_class.name
        'Brevo'
        >>> provider_class = get_provider_by_attribute(config, "display_name", "SMTP")
        >>> provider_class.name
        'smtp'
    """
    if not providers_config or not attribute or not value:
        return None

    # Security: Validate attribute name is safe
    if not _is_safe_attribute_name(attribute):
        return None

    provider_paths, _ = _split_providers_config(providers_config)
    normalized_value = value.strip().lower()

    for provider_path, provider_class in _iter_provider_classes(provider_paths, on_error=on_error):
        attr_value = getattr(provider_class, attribute, None)
        if attr_value is None:
            continue

        attr_str = str(attr_value).strip().lower()
        if attr_str == normalized_value:
            return cast(Type[BaseProviderCommon], provider_class)

    return None


def get_address_backend_by_attribute(
    backends_config: Sequence[Dict[str, Any]] | None = None,
    attribute: str = "",
    value: str = "",
) -> Optional[Type[BaseAddressBackend]]:
    """Get an address backend class by matching an attribute value.

    Args:
        backends_config: List of backend configurations, each with:
            - "class": Import path to backend class
            - "config": Configuration dict for the backend
        attribute: Attribute name to search (e.g., "name").
        value: Value to match (case-insensitive).

    Returns:
        Backend class if found, None otherwise.

    Example:
        >>> config = [
        ...     {
        ...         "class": "python_missive.address_backends.nominatim.NominatimAddressBackend",
        ...         "config": {},
        ...     }
        ... ]
        >>> backend_class = get_address_backend_by_attribute(config, "name", "nominatim")
        >>> backend_class.name
        'nominatim'
    """
    if BaseAddressBackend is None:
        return None

    if not backends_config or not attribute or not value:
        return None

    # Security: Validate attribute name is safe
    if not _is_safe_attribute_name(attribute):
        return None

    normalized_value = value.strip().lower()

    for backend_config in backends_config:
        class_path = backend_config.get("class", "")
        if not class_path:
            continue

        try:
            backend_class = _load_address_backend_class(class_path)
            attr_value = getattr(backend_class, attribute, None)
            if attr_value is None:
                continue

            attr_str = str(attr_value).strip().lower()
            if attr_str == normalized_value:
                return backend_class
        except (ImportError, AttributeError, ValueError):
            # Backend class not found or invalid, skip
            continue

    return None


def _has_critical_error(errors: List[str]) -> bool:
    """Check if errors list contains critical errors."""
    if not errors:
        return False
    for error in errors:
        error_lower = str(error).lower()
        if (
            "not configured" in error_lower
            or "not installed" in error_lower
            or ("error" in error_lower and "no address found" not in error_lower)
        ):
            return True
    return False


def _try_validate_backend(
    backend: Any, address_kwargs: Dict[str, Any], threshold: float
) -> Optional[Dict[str, Any]]:
    """Try validate_address on a backend, return result if successful."""
    try:
        validate_result: Dict[str, Any] = backend.validate_address(**address_kwargs)
        errors = validate_result.get("errors", [])

        if _has_critical_error(errors):
            return None

        suggestions = validate_result.get("suggestions") or []
        filtered_suggestions = [
            s for s in suggestions if _passes_min_confidence(s.get("confidence"), threshold)
        ]
        validate_result["suggestions"] = filtered_suggestions

        if filtered_suggestions or validate_result.get("normalized_address"):
            validate_result["backend_used"] = backend.name
            return validate_result
    except Exception:
        pass
    return None


def _try_geocode_backend(
    backend: Any, address_kwargs: Dict[str, Any], threshold: float
) -> Optional[Dict[str, Any]]:
    """Try geocode on a backend, return result if successful."""
    try:
        geocode_result: Dict[str, Any] = backend.geocode(**address_kwargs)
        errors = geocode_result.get("errors", [])

        if _has_critical_error(errors):
            return None

        if geocode_result.get("normalized_address") or geocode_result.get("latitude"):
            confidence_ok = _passes_min_confidence(geocode_result.get("confidence"), threshold)
            if confidence_ok or geocode_result.get("confidence") is None:
                geocode_result["backend_used"] = backend.name
                return geocode_result
    except Exception:
        pass
    return None


def _build_normalized_result(
    normalized: Dict[str, Any], result: Dict[str, Any], query: str
) -> Dict[str, Any]:
    """Build a normalized result dictionary from backend response."""
    normalized_result = dict(normalized)
    normalized_result["formatted_address"] = (
        normalized_result.get("formatted_address") or result.get("formatted_address") or query
    )
    normalized_result["confidence"] = (
        result.get("confidence") or normalized_result.get("confidence") or 0.0
    )
    normalized_result["backend_used"] = result.get("backend_used")
    normalized_result["address_reference"] = normalized_result.get(
        "address_reference"
    ) or result.get("address_reference")
    return normalized_result


def _parse_address_query(query: str) -> Dict[str, Optional[str]]:
    """Parse an address search string to extract components.

    Tries to extract postal_code (5 digits) and city from the query string.
    This helps improve search results by providing structured hints to backends.

    Args:
        query: Address search string (e.g., "35 rue jean jaures 60870 villers")

    Returns:
        Dictionary with parsed components:
        - address_line1: Street address part
        - postal_code: Extracted postal code (5 digits)
        - city: City name after postal code
    """
    import re

    query = query.strip()
    if not query:
        return {"address_line1": query, "postal_code": None, "city": None}

    # Try to extract postal code (5 digits pattern, works for FR, US, etc.)
    postal_code_pattern = r"\b(\d{5})\b"
    postal_match = re.search(postal_code_pattern, query)

    postal_code = None
    city = None
    address_line1 = query

    if postal_match:
        postal_code = postal_match.group(1)
        postal_pos = postal_match.start()

        parts = query.split(postal_code)
        if len(parts) >= 2:
            address_line1 = parts[0].strip()
            city_part = parts[1].strip()
            if city_part:
                city = city_part
        else:
            address_line1 = query[:postal_pos].strip()

    return {
        "address_line1": address_line1,
        "postal_code": postal_code,
        "city": city,
    }


def search_addresses(
    backends_config: Sequence[Dict[str, Any]] | None = None,
    query: str = "",
    country: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 10,
    backend: Optional[str | List[str]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Search for addresses using a simple query string.

    This is a simplified interface that accepts a single search string and returns
    the closest matching addresses sorted by confidence. It's designed for user
    input scenarios where addresses are entered as free text.

    Args:
        backends_config: List of backend configurations. If None, returns error.
        query: Address search string (e.g., "35 rue jean jaures 60870 villers").
        country: Optional ISO country code (e.g., "FR", "US") to filter results.
        min_confidence: Optional minimum confidence (0-1) for results. Defaults to
            ``PYTHON_MISSIVE_MIN_ADDRESS_CONFIDENCE`` env var or 0.4.
        limit: Maximum number of results to return (default: 10).
        backend: Optional backend name(s) to use exclusively. Can be:
            - A single backend name (e.g., "nominatim")
            - A list of backend names (e.g., ["nominatim", "google_maps"])
            - None to try all configured backends in sequence.
            Case-insensitive.
        **kwargs: Additional options passed to backends.

    Returns:
        Dictionary with search results:
        - results (list): List of matching addresses, sorted by confidence (highest first).
            Each result contains:
            - formatted_address (str): Full formatted address
            - address_line1, address_line2, city, postal_code, etc.
            - latitude, longitude (float, optional): Coordinates
            - confidence (float): Confidence score (0.0-1.0)
            - address_reference (str): Reference ID for reverse lookup
        - total (int): Total number of results found
        - backend_used (str): Name of the backend that provided results
        - error (str, optional): Error message if search failed
        - errors (list, optional): List of error messages

    Example:
        >>> config = [{"class": "python_missive.address_backends.nominatim.NominatimAddressBackend", "config": {}}]
        >>> result = search_addresses(config, "35 rue jean jaures 60870 villers")
        >>> len(result.get("results", []))
        3
        >>> result["results"][0]["confidence"] >= result["results"][1]["confidence"]
        True
        >>> # Force a specific backend
        >>> result = search_addresses(config, "35 rue jean jaures 60870 villers", backend="nominatim")
        >>> # Or use multiple backends
        >>> result = search_addresses(config, "35 rue jean jaures 60870 villers", backend=["nominatim", "google_maps"])
    """
    if not query or not isinstance(query, str):
        return {
            "results": [],
            "total": 0,
            "error": "Empty or invalid query",
            "errors": ["Query string is required"],
        }

    # Pour la recherche, on utilise toujours la requête brute sans reconstruction
    # Les backends sont conçus pour gérer les requêtes en langage naturel
    address_kwargs = {
        "query": query,  # Passer la requête brute directement
        "country": country,
    }

    # Get backends
    if not backends_config:
        return {
            "results": [],
            "total": 0,
            "error": "No backends configuration provided",
            "errors": ["No address backends configured"],
        }

    # Filter configs by backend name(s) if specified, so we only load those backends
    filtered_configs = backends_config
    if backend:
        filtered_configs = _filter_backend_configs_by_name(backends_config, backend)
        if not filtered_configs:
            # Try to get available backend names for error message
            try:
                temp_backends = get_address_backends_from_config(backends_config)
                available_backends = ", ".join(
                    sorted(set(getattr(b, "name", "unknown") for b in temp_backends))
                )
            except Exception:
                available_backends = "unknown"
            backend_display = (
                backend if isinstance(backend, str) else ", ".join(str(b) for b in backend)
            )
            return {
                "results": [],
                "total": 0,
                "error": f"Backend(s) '{backend_display}' not found",
                "errors": [
                    f"Backend(s) '{backend_display}' is not available. Available backends: {available_backends}"
                ],
            }

    # Now load only the filtered backends (will be just the specified ones if backend was specified)
    backends = get_address_backends_from_config(filtered_configs)

    if not backends:
        return {
            "results": [],
            "total": 0,
            "error": "No working backends found",
            "errors": ["No address backends are properly configured"],
        }

    threshold = _resolve_min_confidence(min_confidence)
    result: Dict[str, Any] = {}

    # Use validate operation only (returns normalized address with lat/lon and suggestions)
    for backend_instance in backends:
        validate_result = _try_validate_backend(backend_instance, address_kwargs, threshold)
        if validate_result:
            result = validate_result
            break

    # Collect all suggestions
    all_results: List[Dict[str, Any]] = []

    # Add normalized address as primary result if available
    normalized = result.get("normalized_address") or {}
    if normalized:
        all_results.append(_build_normalized_result(normalized, result, query))

    # Add suggestions
    suggestions = result.get("suggestions") or []
    for suggestion in suggestions:
        suggestion_copy = dict(suggestion)
        suggestion_copy["backend_used"] = result.get("backend_used")
        if suggestion_copy not in all_results:  # Avoid duplicates
            all_results.append(suggestion_copy)

    # Sort by confidence (highest first)
    def _get_confidence(item: Dict[str, Any]) -> float:
        conf = _coerce_confidence(item.get("confidence"))
        return conf if conf is not None else 0.0

    all_results.sort(key=_get_confidence, reverse=True)

    # Apply limit
    limited_results = all_results[:limit]

    # Build response
    response: Dict[str, Any] = {
        "results": limited_results,
        "total": len(all_results),
    }

    if result.get("backend_used"):
        response["backend_used"] = result["backend_used"]

    if result.get("error"):
        response["error"] = result["error"]
        response["errors"] = result.get("errors", [])

    return response
