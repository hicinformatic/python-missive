"""Geoapify API address verification backend."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, cast

import requests

from .base import BaseAddressBackend


class GeoapifyAddressBackend(BaseAddressBackend):
    """Geoapify Geocoding API backend for address verification.

    Geoapify provides geocoding, reverse geocoding, and autocomplete services.
    Free tier: 3000 requests/day.
    Requires API key (free registration).
    """

    name = "geoapify"
    display_name = "Geoapify"
    config_keys = ["GEOAPIFY_API_KEY", "GEOAPIFY_BASE_URL"]
    required_packages = ["requests"]
    documentation_url = "https://apidocs.geoapify.com/docs/geocoding/"
    site_url = "https://www.geoapify.com"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Geoapify backend.

        Args:
            config: Optional configuration dict with:
                - GEOAPIFY_API_KEY: API key (required)
                - GEOAPIFY_BASE_URL: Custom base URL (default: official)
        """
        super().__init__(config)
        self._api_key = self._config.get("GEOAPIFY_API_KEY")
        if not self._api_key:
            raise ValueError("GEOAPIFY_API_KEY is required")
        self._base_url = self._config.get("GEOAPIFY_BASE_URL", "https://api.geoapify.com/v1")
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
        """Respect Geoapify rate limit (10 requests per second)."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < 0.1:  # 1/10 second = 10 requests/second
            time.sleep(0.1 - time_since_last)
        self._last_request_time = time.time()

    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the Geoapify API."""
        self._rate_limit()

        url = f"{self._base_url}{endpoint}"

        request_params: Dict[str, Any] = {"apiKey": self._api_key}
        if params:
            request_params.update(params)

        try:
            response = requests.get(url, params=request_params, timeout=10)
            response.raise_for_status()
            return cast(Dict[str, Any], response.json())
        except requests.exceptions.HTTPError as e:
            try:
                error_data = response.json()
                error_msg = error_data.get("message", str(e))
            except Exception:
                error_msg = str(e)
            return {"error": error_msg}
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def _extract_address_from_feature(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address components from a Geoapify feature."""
        properties = feature.get("properties", {})

        # Geoapify provides address_line1 directly, or build from housenumber and street
        address_line1 = properties.get("address_line1", "")
        if not address_line1:
            address_line1_parts = []
            if properties.get("housenumber"):
                address_line1_parts.append(str(properties["housenumber"]))
            if properties.get("street"):
                address_line1_parts.append(properties["street"])
            address_line1 = " ".join(address_line1_parts).strip()

        # Extract coordinates - Geoapify provides lat/lon directly in properties
        latitude = None
        longitude = None
        if "lat" in properties and properties["lat"] is not None:
            latitude = float(properties["lat"])
        if "lon" in properties and properties["lon"] is not None:
            longitude = float(properties["lon"])

        # Fallback to geometry if not in properties (GeoJSON format: [longitude, latitude])
        if latitude is None or longitude is None:
            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates", [])
            if len(coordinates) >= 2:
                if longitude is None:
                    longitude = float(coordinates[0])
                if latitude is None:
                    latitude = float(coordinates[1])

        # Extract confidence - Geoapify provides it as 0-1 scale in rank.confidence
        confidence = 0.0
        rank = properties.get("rank", {})
        if rank and "confidence" in rank:
            confidence = float(rank["confidence"])

        return {
            "address_line1": address_line1 or "",
            "address_line2": properties.get("district", "") or properties.get("suburb", ""),
            "address_line3": properties.get("neighbourhood", ""),
            "city": properties.get("city", "")
            or properties.get("town", "")
            or properties.get("village", "")
            or properties.get("municipality", ""),
            "postal_code": properties.get("postcode", ""),
            "state": properties.get("state", "") or properties.get("state_code", ""),
            "country": (
                properties.get("country_code", "").upper() if properties.get("country_code") else ""
            ),
            "address_reference": properties.get("place_id") or feature.get("id"),
            "latitude": latitude,
            "longitude": longitude,
            "confidence": confidence,
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
        """Validate an address using Geoapify autocomplete API."""
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

        params: Dict[str, Any] = {"text": query_string, "limit": 5}
        if country:
            params["filter"] = f"countrycode:{country.upper()}"

        result = self._make_request("/geocode/autocomplete", params)

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
                        "formatted_address": feature.get("properties", {}).get("formatted", ""),
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
        """Geocode an address to coordinates using Geoapify."""
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

        params: Dict[str, Any] = {"text": query_string, "limit": 1}
        if country:
            params["filter"] = f"countrycode:{country.upper()}"

        result = self._make_request("/geocode/search", params)

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
            "accuracy": "ROOFTOP",  # Geoapify doesn't provide explicit accuracy
            "confidence": normalized.get("confidence", 0.0),
            "formatted_address": best_match.get("properties", {}).get("formatted", ""),
            "address_reference": normalized.get("address_reference"),
            "errors": [],
        }

    def reverse_geocode(self, latitude: float, longitude: float, **kwargs: Any) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using Geoapify."""
        params: Dict[str, Any] = {"lat": latitude, "lon": longitude}
        if "language" in kwargs:
            params["lang"] = kwargs["language"]

        result = self._make_request("/geocode/reverse", params)

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
            "formatted_address": best_match.get("properties", {}).get("formatted", ""),
            "latitude": normalized.get("latitude", latitude),
            "longitude": normalized.get("longitude", longitude),
            "confidence": normalized.get("confidence", 0.0),
            "address_reference": normalized.get("address_reference"),
            "errors": [],
        }

    def get_address_by_reference(self, address_reference: str, **kwargs: Any) -> Dict[str, Any]:
        """Retrieve address details by a reference ID using Geoapify.

        Geoapify supports lookup by place_id.
        """
        params: Dict[str, Any] = {"place_id": address_reference}
        result = self._make_request("/geocode/search", params)

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
            "formatted_address": best_match.get("properties", {}).get("formatted", ""),
            "confidence": normalized.get("confidence", 0.0),
            "address_reference": normalized.get("address_reference"),
            "errors": [],
        }
