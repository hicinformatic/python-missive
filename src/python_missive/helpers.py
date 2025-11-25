"""Framework-agnostic helpers for provider discovery."""

from __future__ import annotations

import csv
import re
from functools import cmp_to_key
from pathlib import Path
from typing import (Any, Callable, Dict, Iterable, List, Mapping, Optional,
                    Sequence, Tuple, Type, cast)

try:
    from .address_backends import BaseAddressBackend
except ImportError:
    BaseAddressBackend = None  # type: ignore[assignment, misc]

from .providers import (BaseProviderCommon, ProviderImportError,
                        get_provider_name_from_path, load_provider_class)

ErrorHandler = Callable[[str, Exception], None]
_ProvidersConfig = Sequence[str] | Mapping[str, Mapping[str, Any]]

# Cache for country phone codes
_COUNTRY_PHONE_CODES: Dict[str, List[str]] = {}


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
        identifier = (
            provider_path if use_paths else get_provider_name_from_path(provider_path)
        )
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
    return _group_providers_by_type(
        providers_config, use_paths=False, on_error=on_error
    )


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

    for provider_path, provider_class in _iter_provider_classes(
        provider_paths, on_error=on_error
    ):
        if target_type not in getattr(provider_class, "supported_types", []):
            continue

        identifier = (
            provider_path if use_paths else get_provider_name_from_path(provider_path)
        )
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
    valid_order_fields = _get_valid_order_fields(
        provider_paths, target_type, config_fields_attr
    )

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

    def _extract_value(
        metadata: Mapping[str, Any], field: str, provider_class: Any
    ) -> Any:
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
                    config_status.get(key) == "present" and config.get(key)
                    for key in required_keys
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


def _mask_value(value: Any) -> Optional[str]:
    if not value:
        return None
    value_str = str(value)
    if len(value_str) <= 6:
        return value_str
    return f"{value_str[:3]}…{value_str[-2:]}"


def _build_backend_diagnostic(
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
        backend_instance = working_instances.get(class_name) or backend_class(
            config=config
        )
        check = backend_instance.check_package_and_config()
        packages = check.get("packages", {})
        config_status = check.get("config", {})
        missing_packages = [
            pkg for pkg, status in packages.items() if status != "installed"
        ]
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
        data["error"] = str(exc)

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
    if skip_api_test:
        sample_result = {"error": "API test skipped", "backend_used": None}
        selected_backend = None
    else:
        sample_result = get_address_from_backends(
            backends_config,
            operation=normalized_operation,
            **resolved_address_kwargs,
            **extra_kwargs_for_call,
        )
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

    for provider_path, provider_class in _iter_provider_classes(
        provider_paths, on_error=on_error
    ):
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


def get_address_from_backends(
    backends_config: Sequence[Dict[str, Any]] | None = None,
    operation: str = "validate",
    address_line1: Optional[str] = None,
    address_line2: Optional[str] = None,
    address_line3: Optional[str] = None,
    city: Optional[str] = None,
    postal_code: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Get address information by trying backends in order until one succeeds.

    Tries each configured backend in order until one successfully processes
    the address request. Falls back to the next backend if one fails.

    Args:
        backends_config: List of backend configurations. If None, returns error.
        operation: Operation to perform: "validate", "geocode", or "reverse_geocode".
        address_line1: Street number and name.
        address_line2: Building, apartment, floor (optional).
        address_line3: Additional address info (optional).
        city: City name.
        postal_code: Postal/ZIP code.
        state: State/region/province.
        country: ISO country code (e.g., "FR", "US", "GB").
        **kwargs: Additional arguments (e.g., latitude, longitude for reverse_geocode).

    Returns:
        Dictionary with operation results from the first successful backend,
        or error information if all backends fail.

    Example:
        >>> config = [{"class": "...", "config": {}}]
        >>> result = get_address_from_backends(
        ...     config,
        ...     operation="validate",
        ...     address_line1="123 Main St",
        ...     city="Paris",
        ...     country="FR"
        ... )
        >>> result.get("is_valid")
        True
    """
    if not backends_config:
        return {
            "error": "No backends configuration provided",
            "errors": ["No address backends configured"],
        }

    backends = get_address_backends_from_config(backends_config)

    if not backends:
        return {
            "error": "No working backends found",
            "errors": ["No address backends are properly configured"],
        }

    address_kwargs = {
        "address_line1": address_line1,
        "address_line2": address_line2,
        "address_line3": address_line3,
        "city": city,
        "postal_code": postal_code,
        "state": state,
        "country": country,
    }

    for backend in backends:
        try:
            if operation == "validate":
                result = backend.validate_address(**address_kwargs)
            elif operation == "geocode":
                result = backend.geocode(**address_kwargs)
            elif operation == "reverse_geocode":
                latitude = kwargs.get("latitude")
                longitude = kwargs.get("longitude")
                if latitude is None or longitude is None:
                    continue
                result = backend.reverse_geocode(latitude, longitude, **kwargs)
            else:
                result = {"error": f"Unknown operation: {operation}"}

            # Check if result indicates a critical error
            errors = result.get("errors", [])
            critical_errors = [
                e
                for e in errors
                if "not configured" in e.lower()
                or "not installed" in e.lower()
                or ("error" in e.lower() and "no address found" not in e.lower())
            ]

            # If no critical errors, return the result
            if not critical_errors:
                result["backend_used"] = backend.name
                return result

        except Exception:
            # Backend failed, try next one
            continue

    # All backends failed
    return {
        "error": "All backends failed",
        "errors": ["All configured address backends failed to process the request"],
    }
