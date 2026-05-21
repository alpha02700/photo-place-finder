"""
Google Maps Platform wrappers: reverse-geocoding + nearby-place search.

Uses the official `googlemaps` Python client which calls the
classic Places API (Nearby Search) under the hood.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import googlemaps


# Mapping from a category label shown in the UI to a Google Places "type".
# See https://developers.google.com/maps/documentation/places/web-service/supported_types
CATEGORY_TYPES: Dict[str, str] = {
    "restaurant": "restaurant",
    "cafe": "cafe",
    "tourist_attraction": "tourist_attraction",
}

# Human-readable Korean labels for each category.
CATEGORY_LABELS_KO: Dict[str, str] = {
    "restaurant": "🍽️ 주변 맛집",
    "cafe": "☕ 카페 / 디저트",
    "tourist_attraction": "🗺️ 관광 명소",
}

# Pin colors for folium markers per category.
CATEGORY_COLORS: Dict[str, str] = {
    "restaurant": "red",
    "cafe": "orange",
    "tourist_attraction": "blue",
}


@dataclass
class Place:
    """Lightweight representation of a Google Place result."""

    place_id: str
    name: str
    category: str
    latitude: float
    longitude: float
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    address: Optional[str] = None
    photo_reference: Optional[str] = None
    types: List[str] = field(default_factory=list)
    open_now: Optional[bool] = None
    distance_m: Optional[float] = None  # metres from the photo location

    @property
    def google_maps_url(self) -> str:
        return (
            "https://www.google.com/maps/search/?api=1"
            f"&query={self.latitude},{self.longitude}"
            f"&query_place_id={self.place_id}"
        )

    def photo_url(self, api_key: str, max_width: int = 400) -> Optional[str]:
        if not self.photo_reference:
            return None
        return (
            "https://maps.googleapis.com/maps/api/place/photo"
            f"?maxwidth={max_width}"
            f"&photo_reference={self.photo_reference}"
            f"&key={api_key}"
        )

    @property
    def distance_label(self) -> str:
        if self.distance_m is None:
            return ""
        if self.distance_m < 1000:
            return f"{self.distance_m:.0f}m"
        return f"{self.distance_m / 1000:.1f}km"


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in metres between two coordinates."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class PlacesClient:
    """Thin wrapper around googlemaps.Client for our two use cases."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("Google Maps API key is required.")
        self.api_key = api_key
        self.gmaps = googlemaps.Client(key=api_key)

    # ------------------------------------------------------------------
    # Reverse geocoding
    # ------------------------------------------------------------------
    def reverse_geocode(
        self, latitude: float, longitude: float, language: str = "ko"
    ) -> Optional[str]:
        """Return a formatted address for a coordinate, or None."""
        try:
            results = self.gmaps.reverse_geocode(
                (latitude, longitude), language=language
            )
        except Exception:
            return None
        if not results:
            return None
        return results[0].get("formatted_address")

    # ------------------------------------------------------------------
    # Forward geocoding (search query → lat/lng)
    # ------------------------------------------------------------------
    def geocode(
        self, query: str, language: str = "ko"
    ) -> Optional[Tuple[float, float]]:
        """Return (lat, lng) for a text search query, or None."""
        try:
            results = self.gmaps.geocode(query, language=language)
        except Exception:
            return None
        if not results:
            return None
        loc = results[0].get("geometry", {}).get("location", {})
        lat = loc.get("lat")
        lng = loc.get("lng")
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)

    # ------------------------------------------------------------------
    # Nearby search
    # ------------------------------------------------------------------
    def nearby(
        self,
        latitude: float,
        longitude: float,
        category: str,
        radius_m: int = 1000,
        max_results: int = 8,
        language: str = "ko",
        sort_by: str = "prominence",  # "prominence" | "rating" | "distance"
    ) -> List[Place]:
        """
        Search Google Places within `radius_m` meters of the coordinate.

        `sort_by` controls client-side re-ordering after the API call:
          - "prominence": Google's default ranking
          - "rating": highest rated first
          - "distance": nearest first
        """
        place_type = CATEGORY_TYPES.get(category)
        if not place_type:
            raise ValueError(f"Unknown category: {category}")

        try:
            resp = self.gmaps.places_nearby(
                location=(latitude, longitude),
                radius=radius_m,
                type=place_type,
                language=language,
            )
        except Exception as e:
            raise RuntimeError(f"Places API request failed: {e}") from e

        places: List[Place] = []
        for item in resp.get("results", [])[:max_results]:
            loc = item.get("geometry", {}).get("location", {})
            lat = loc.get("lat")
            lng = loc.get("lng")
            if lat is None or lng is None:
                continue

            photos = item.get("photos") or []
            photo_ref = photos[0].get("photo_reference") if photos else None

            opening = item.get("opening_hours") or {}
            open_now = opening.get("open_now")

            dist = haversine_m(latitude, longitude, float(lat), float(lng))

            places.append(
                Place(
                    place_id=item.get("place_id", ""),
                    name=item.get("name", "Unknown"),
                    category=category,
                    latitude=float(lat),
                    longitude=float(lng),
                    rating=item.get("rating"),
                    user_ratings_total=item.get("user_ratings_total"),
                    address=item.get("vicinity") or item.get("formatted_address"),
                    photo_reference=photo_ref,
                    types=item.get("types", []),
                    open_now=open_now,
                    distance_m=dist,
                )
            )

        if sort_by == "rating":
            places.sort(key=lambda p: p.rating or 0.0, reverse=True)
        elif sort_by == "distance":
            places.sort(key=lambda p: p.distance_m or float("inf"))

        return places
