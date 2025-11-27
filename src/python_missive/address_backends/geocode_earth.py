"""Geocode Earth API address verification backend."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, cast

import requests

from .base import BaseAddressBackend


class GeocodeEarthAddressBackend(BaseAddressBackend):
    """Geocode Earth Geocoding API backend for address verification.

    Geocode Earth is a Pelias-based geocoding service.
    Uses the /autocomplete endpoint for optimized address suggestions.
    Free tier: Limited requests/day (check documentation).
    Requires API key (free registration).
    """

    name = "geocode_earth"
    display_name = "Geocode Earth"
    config_keys = ["GEOCODE_EARTH_API_KEY", "GEOCODE_EARTH_BASE_URL"]
    required_packages = ["requests"]
    documentation_url = "https://geocode.earth/docs"
    site_url = "https://geocode.earth"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Geocode Earth backend.

        Args:
            config: Optional configuration dict with:
                - GEOCODE_EARTH_API_KEY: API key (required)
                - GEOCODE_EARTH_BASE_URL: Custom base URL (default: official)
        """
        super().__init__(config)
        self._api_key = self._config.get("GEOCODE_EARTH_API_KEY")
        if not self._api_key:
            raise ValueError("GEOCODE_EARTH_API_KEY is required")
        self._base_url = self._config.get("GEOCODE_EARTH_BASE_URL", "https://api.geocode.earth/v1")
        self._last_request_time = 0.0

    def _build_address_string(
        self,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        address_line3: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
    ) -> str:
        """Build a query string from address components."""
        parts = []
        if address_line1:
            parts.append(address_line1)
        if address_line2:
            parts.append(address_line2)
        if address_line3:
            parts.append(address_line3)
        if city:
            parts.append(city)
        if postal_code:
            parts.append(postal_code)
        if state:
            parts.append(state)
        if country:
            parts.append(country)
        return ", ".join(filter(None, parts))

    def _rate_limit(self) -> None:
        """Respect Geocode Earth rate limit (2 requests per second)."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < 0.5:  # 1/2 second = 2 requests/second
            time.sleep(0.5 - time_since_last)
        self._last_request_time = time.time()

    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the Geocode Earth API."""
        self._rate_limit()

        url = f"{self._base_url}{endpoint}"

        request_params: Dict[str, Any] = {"api_key": self._api_key}
        if params:
            request_params.update(params)

        try:
            response = requests.get(url, params=request_params, timeout=10)
            response.raise_for_status()
            return cast(Dict[str, Any], response.json())
        except requests.exceptions.HTTPError as e:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", str(e))
            except Exception:
                error_msg = str(e)
            return {"error": error_msg}
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def _extract_address_from_feature(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address components from a Geocode Earth/Pelias feature."""
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})

        # Build address_line1 from housenumber and street
        address_line1_parts = []
        if properties.get("housenumber"):
            address_line1_parts.append(properties["housenumber"])
        if properties.get("street"):
            address_line1_parts.append(properties["street"])
        address_line1 = " ".join(address_line1_parts).strip()

        # Fallback to name if address_line1 is empty
        if not address_line1:
            address_line1 = properties.get("name", "")

        # Extract coordinates (GeoJSON format: [longitude, latitude])
        coordinates = geometry.get("coordinates", [])
        longitude = None
        latitude = None
        if len(coordinates) >= 2:
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])

        return {
            "address_line1": address_line1 or "",
            "address_line2": properties.get("neighbourhood", ""),
            "address_line3": properties.get("borough", ""),
            "city": properties.get("locality", "")
            or properties.get("localadmin", "")
            or properties.get("county", ""),
            "postal_code": properties.get("postalcode", ""),
            "state": properties.get("region", ""),
            "country": (
                properties.get("country_a", "").upper() if properties.get("country_a") else ""
            ),
            "address_reference": properties.get("gid") or feature.get("id"),
            "latitude": latitude,
            "longitude": longitude,
            "confidence": float(properties.get("confidence", 0.0)),
        }

    def validate_address(
        self,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        address_line3: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Validate an address using Geocode Earth autocomplete API."""
        if query:
            query_string = query
        else:
            query_string = self._build_address_string(
                address_line1,
                address_line2,
                address_line3,
                city,
                postal_code,
                state,
                country,
            )

        if not query_string:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["Address query is empty"],
            }

        params: Dict[str, Any] = {"text": query_string, "size": 5}
        if country:
            params["boundary.country"] = country.upper()

        result = self._make_request("/autocomplete", params)

        if "error" in result:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": [result["error"]],
            }

        features = result.get("features", [])
        if not features:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["No address found"],
            }

        best_match = features[0]
        normalized = self._extract_address_from_feature(best_match)

        confidence = normalized.get("confidence", 0.0)
        is_valid = confidence >= 0.5

        suggestions = []
        if not is_valid and len(features) > 1:
            for feature in features[1:5]:
                suggestion = self._extract_address_from_feature(feature)
                suggestions.append(
                    {
                        "formatted_address": feature.get("properties", {}).get("label", ""),
                        "confidence": suggestion.get("confidence", 0.0),
                        "latitude": suggestion.get("latitude"),
                        "longitude": suggestion.get("longitude"),
                    }
                )

        warnings = []
        if confidence < 0.7:
            warnings.append("Low confidence match")

        return {
            "is_valid": is_valid,
            "normalized_address": normalized,
            "confidence": confidence,
            "suggestions": suggestions,
            "warnings": warnings,
            "errors": [],
            "address_reference": normalized.get("address_reference"),
        }

    def geocode(
        self,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        address_line3: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Geocode an address to coordinates using Geocode Earth autocomplete API."""
        if query:
            query_string = query
        else:
            query_string = self._build_address_string(
                address_line1,
                address_line2,
                address_line3,
                city,
                postal_code,
                state,
                country,
            )

        if not query_string:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["Address query is empty"],
            }

        params: Dict[str, Any] = {"text": query_string, "size": 1}
        if country:
            params["boundary.country"] = country.upper()

        result = self._make_request("/autocomplete", params)

        if "error" in result:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": [result["error"]],
            }

        features = result.get("features", [])
        if not features:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["No address found"],
            }

        best_match = features[0]
        normalized = self._extract_address_from_feature(best_match)

        return {
            "latitude": normalized.get("latitude"),
            "longitude": normalized.get("longitude"),
            "accuracy": "ROOFTOP",  # Geocode Earth doesn't provide explicit accuracy
            "confidence": normalized.get("confidence", 0.0),
            "formatted_address": best_match.get("properties", {}).get("label", ""),
            "address_reference": normalized.get("address_reference"),
            "errors": [],
        }

    def reverse_geocode(self, latitude: float, longitude: float, **kwargs: Any) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using Geocode Earth."""
        params: Dict[str, Any] = {
            "point.lat": latitude,
            "point.lon": longitude,
        }
        if "language" in kwargs:
            params["lang"] = kwargs["language"]

        result = self._make_request("/reverse", params)

        if "error" in result:
            return {
                "address_line1": None,
                "address_line2": None,
                "address_line3": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "latitude": latitude,
                "longitude": longitude,
                "confidence": 0.0,
                "address_reference": None,
                "errors": [result["error"]],
            }

        features = result.get("features", [])
        if not features:
            return {
                "address_line1": None,
                "address_line2": None,
                "address_line3": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "latitude": latitude,
                "longitude": longitude,
                "confidence": 0.0,
                "address_reference": None,
                "errors": ["No address found"],
            }

        best_match = features[0]
        normalized = self._extract_address_from_feature(best_match)

        return {
            **normalized,
            "formatted_address": best_match.get("properties", {}).get("label", ""),
            "latitude": normalized.get("latitude", latitude),
            "longitude": normalized.get("longitude", longitude),
            "confidence": normalized.get("confidence", 0.0),
            "address_reference": normalized.get("address_reference"),
            "errors": [],
        }

    def get_address_by_reference(self, address_reference: str, **kwargs: Any) -> Dict[str, Any]:
        """Retrieve address details by a reference ID using Geocode Earth.

        Geocode Earth uses Pelias which supports lookup by GID (global ID).
        """
        params: Dict[str, Any] = {"ids": address_reference}
        result = self._make_request("/place", params)

        if "error" in result:
            return {
                "address_line1": None,
                "address_line2": None,
                "address_line3": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "latitude": None,
                "longitude": None,
                "confidence": 0.0,
                "address_reference": address_reference,
                "errors": [result["error"]],
            }

        features = result.get("features", [])
        if not features:
            return {
                "address_line1": None,
                "address_line2": None,
                "address_line3": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "latitude": None,
                "longitude": None,
                "confidence": 0.0,
                "address_reference": address_reference,
                "errors": ["Address not found for reference"],
            }

        best_match = features[0]
        normalized = self._extract_address_from_feature(best_match)

        return {
            **normalized,
            "formatted_address": best_match.get("properties", {}).get("label", ""),
            "confidence": normalized.get("confidence", 0.0),
            "address_reference": normalized.get("address_reference"),
            "errors": [],
        }
