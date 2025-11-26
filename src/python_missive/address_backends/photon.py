"""Photon (Komoot) address verification backend."""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from .base import BaseAddressBackend


class PhotonAddressBackend(BaseAddressBackend):
    """Photon (Komoot) Geocoding API backend for address verification.

    Completely free, no API key required. Fast geocoding based on OpenStreetMap data.
    Provided by Komoot.
    """

    name = "photon"
    display_name = "Photon (Komoot)"
    config_keys = ["PHOTON_BASE_URL"]
    required_packages = ["requests"]
    documentation_url = "https://photon.komoot.io/"
    site_url = "https://photon.komoot.io"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Photon backend.

        Args:
            config: Optional configuration dict with:
                - PHOTON_BASE_URL: Custom Photon server URL (default: official)
        """
        super().__init__(config)
        self._base_url = self._config.get("PHOTON_BASE_URL", "https://photon.komoot.io")

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
        """Make a request to the Photon API."""
        try:
            import requests
        except ImportError:
            return {"error": "requests package not installed"}

        url = f"{self._base_url}{endpoint}"

        request_params = {}
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
        """Validate an address using Photon."""
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

        params = {"q": query, "limit": 5}
        if country:
            params["osm_tag"] = f"place:country={country}"

        result = self._make_request("/api", params)

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

        properties = best_match.get("properties", {})
        importance = properties.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)
        is_valid = confidence >= 0.5 and importance >= 0.3

        suggestions = []
        if not is_valid and len(features) > 1:
            for feature in features[1:5]:
                feat_props = feature.get("properties", {})
                feat_importance = feat_props.get("importance", 0.0)
                suggestions.append(
                    {
                        "formatted_address": feat_props.get("name", ""),
                        "confidence": min(feat_importance * 2.0, 1.0),
                    }
                )

        warnings = []
        if importance < 0.5:
            warnings.append("Low importance match")
        if confidence < 0.7:
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
        """Geocode an address to coordinates using Photon."""
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

        params = {"q": query, "limit": 1}
        if country:
            params["osm_tag"] = f"place:country={country}"

        result = self._make_request("/api", params)

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

        osm_type = properties.get("osm_type", "")
        osm_key = properties.get("osm_key", "")
        accuracy_map = {
            "node": "ROOFTOP" if osm_key == "place" else "STREET",
            "way": "STREET",
            "relation": "CITY",
        }
        accuracy = accuracy_map.get(osm_type, "UNKNOWN")

        importance = properties.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)

        return {
            "latitude": coordinates[1] if len(coordinates) >= 2 else None,
            "longitude": coordinates[0] if len(coordinates) >= 1 else None,
            "accuracy": accuracy,
            "confidence": confidence,
            "formatted_address": properties.get("name", ""),
            "errors": [],
        }

    def reverse_geocode(
        self, latitude: float, longitude: float, **kwargs: Any
    ) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using Photon."""
        params = {"lat": str(latitude), "lon": str(longitude), "limit": 1}
        if "language" in kwargs:
            params["lang"] = kwargs["language"]

        result = self._make_request("/reverse", params)

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

        properties = feature.get("properties", {})
        importance = properties.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)

        return {
            **normalized,
            "formatted_address": properties.get("name", ""),
            "confidence": confidence,
            "errors": [],
        }

    def _extract_address_from_feature(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address components from a Photon feature."""
        properties = feature.get("properties", {})

        address_line1 = ""
        house_number = properties.get("housenumber", "")
        street = properties.get("street", "")
        if house_number and street:
            address_line1 = f"{house_number} {street}".strip()
        elif street:
            address_line1 = street

        city = (
            properties.get("city")
            or properties.get("town")
            or properties.get("village")
            or ""
        )
        postal_code = properties.get("postcode", "")
        state = properties.get("state", "")
        country = properties.get("countrycode", "").upper()

        return {
            "address_line1": address_line1,
            "address_line2": "",
            "address_line3": "",
            "city": city,
            "postal_code": postal_code,
            "state": state,
            "country": country,
        }
