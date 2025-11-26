"""Mapbox address verification backend."""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from .base import BaseAddressBackend


class MapboxAddressBackend(BaseAddressBackend):
    """Mapbox Geocoding API backend for address verification.

    Requires the `requests` package and a Mapbox access token.
    """

    name = "mapbox"
    display_name = "Mapbox"
    config_keys = ["MAPBOX_ACCESS_TOKEN"]
    required_packages = ["requests"]
    documentation_url = "https://docs.mapbox.com/api/search/geocoding/"
    site_url = "https://www.mapbox.com"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Mapbox backend.

        Args:
            config: Configuration dict with MAPBOX_ACCESS_TOKEN.
        """
        super().__init__(config)
        self._access_token = self._config.get("MAPBOX_ACCESS_TOKEN")

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
        if city:
            parts.append(city)
        if postal_code:
            parts.append(postal_code)
        if state:
            parts.append(state)
        if country:
            parts.append(country)
        return ", ".join(filter(None, parts))

    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the Mapbox API."""
        if not self._access_token:
            return {"error": "MAPBOX_ACCESS_TOKEN not configured"}

        try:
            import requests
        except ImportError:
            return {"error": "requests package not installed"}

        base_url = "https://api.mapbox.com"
        url = f"{base_url}{endpoint}"

        request_params: Dict[str, Any] = {"access_token": self._access_token}
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

    def validate_address(
        self,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        address_line3: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Validate an address using Mapbox Geocoding API."""
        query = self._build_address_string(
            address_line1,
            address_line2,
            address_line3,
            city,
            postal_code,
            state,
            country,
        )

        if not query:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["Address query is empty"],
            }

        import urllib.parse

        encoded_query = urllib.parse.quote(query)
        params: Dict[str, Any] = {"limit": 5}
        if country:
            params["country"] = country

        result = self._make_request(
            f"/geocoding/v5/mapbox.places/{encoded_query}.json", params
        )

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

        confidence = best_match.get("relevance", 0.0)
        is_valid = confidence >= 0.7

        suggestions = []
        if not is_valid and len(features) > 1:
            for feature in features[1:]:
                suggestions.append(
                    {
                        "formatted_address": feature.get("place_name", ""),
                        "confidence": feature.get("relevance", 0.0),
                    }
                )

        warnings = []
        if confidence < 0.9:
            warnings.append("Low confidence match")

        return {
            "is_valid": is_valid,
            "normalized_address": normalized,
            "confidence": confidence,
            "suggestions": suggestions,
            "warnings": warnings,
            "errors": [],
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
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Geocode an address to coordinates using Mapbox."""
        query = self._build_address_string(
            address_line1,
            address_line2,
            address_line3,
            city,
            postal_code,
            state,
            country,
        )

        if not query:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["Address query is empty"],
            }

        import urllib.parse

        encoded_query = urllib.parse.quote(query)
        params: Dict[str, Any] = {"limit": 1}
        if country:
            params["country"] = country

        result = self._make_request(
            f"/geocoding/v5/mapbox.places/{encoded_query}.json", params
        )

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

        feature = features[0]
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        properties = feature.get("properties", {})

        accuracy_map = {
            "address": "ROOFTOP",
            "poi": "ROOFTOP",
            "neighborhood": "STREET",
            "locality": "CITY",
            "place": "CITY",
            "district": "CITY",
            "region": "REGION",
            "country": "COUNTRY",
        }
        accuracy = accuracy_map.get(properties.get("type", ""), "UNKNOWN")

        return {
            "latitude": coordinates[1] if len(coordinates) >= 2 else None,
            "longitude": coordinates[0] if len(coordinates) >= 1 else None,
            "accuracy": accuracy,
            "confidence": feature.get("relevance", 0.0),
            "formatted_address": feature.get("place_name", ""),
            "errors": [],
        }

    def reverse_geocode(
        self, latitude: float, longitude: float, **kwargs: Any
    ) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using Mapbox."""
        params: Dict[str, Any] = {"limit": 1}
        if "language" in kwargs:
            params["language"] = kwargs["language"]

        result = self._make_request(
            f"/geocoding/v5/mapbox.places/{longitude},{latitude}.json", params
        )

        if "error" in result:
            return {
                "address_line1": None,
                "address_line2": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "confidence": 0.0,
                "errors": [result["error"]],
            }

        features = result.get("features", [])
        if not features:
            return {
                "address_line1": None,
                "address_line2": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "confidence": 0.0,
                "errors": ["No address found"],
            }

        feature = features[0]
        normalized = self._extract_address_from_feature(feature)

        return {
            **normalized,
            "formatted_address": feature.get("place_name", ""),
            "confidence": feature.get("relevance", 0.0),
            "errors": [],
        }

    def _extract_address_from_feature(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address components from a Mapbox feature."""
        properties = feature.get("properties", {})
        context = feature.get("context", [])

        address_line1 = properties.get("address", "")
        city = None
        postal_code = None
        state = None
        country = None

        for item in context:
            item_id = item.get("id", "")
            if item_id.startswith("postcode"):
                postal_code = item.get("text", "")
            elif item_id.startswith("place"):
                city = item.get("text", "")
            elif item_id.startswith("region"):
                state = item.get("text", "")
            elif item_id.startswith("country"):
                country = item.get("short_code", "").upper()

        return {
            "address_line1": address_line1 or "",
            "address_line2": "",
            "address_line3": "",
            "city": city or "",
            "postal_code": postal_code or "",
            "state": state or "",
            "country": country or "",
        }
