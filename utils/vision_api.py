"""
Google Cloud Vision API wrapper for landmark detection.

Uses the REST endpoint (https://vision.googleapis.com/v1/images:annotate)
with an API key, so users don't need a service-account JSON file.
"""
from __future__ import annotations

import base64
from typing import List, Optional

import requests


VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"


class LandmarkResult:
    """Simple container for a detected landmark."""

    def __init__(
        self,
        description: str,
        score: float,
        latitude: float,
        longitude: float,
    ) -> None:
        self.description = description
        self.score = score
        self.latitude = latitude
        self.longitude = longitude

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"LandmarkResult({self.description!r}, score={self.score:.2f}, "
            f"lat={self.latitude:.5f}, lng={self.longitude:.5f})"
        )


def detect_landmarks(
    image_bytes: bytes,
    api_key: str,
    max_results: int = 5,
    timeout: int = 30,
) -> List[LandmarkResult]:
    """
    Send an image to Vision API and return a list of detected landmarks
    sorted by confidence score (highest first).
    """
    if not api_key:
        raise ValueError("Vision API key is required.")

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "requests": [
            {
                "image": {"content": encoded},
                "features": [
                    {"type": "LANDMARK_DETECTION", "maxResults": max_results}
                ],
            }
        ]
    }

    response = requests.post(
        VISION_ENDPOINT,
        params={"key": api_key},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    landmarks: List[LandmarkResult] = []
    for resp in data.get("responses", []):
        if "error" in resp:
            # Surface helpful error message to the caller.
            raise RuntimeError(
                f"Vision API error: {resp['error'].get('message', 'unknown')}"
            )
        for ann in resp.get("landmarkAnnotations", []):
            description = ann.get("description", "Unknown")
            score = float(ann.get("score", 0.0))
            locations = ann.get("locations") or []
            if not locations:
                continue
            latlng = locations[0].get("latLng") or {}
            lat = latlng.get("latitude")
            lng = latlng.get("longitude")
            if lat is None or lng is None:
                continue
            landmarks.append(
                LandmarkResult(
                    description=description,
                    score=score,
                    latitude=float(lat),
                    longitude=float(lng),
                )
            )

    landmarks.sort(key=lambda x: x.score, reverse=True)
    return landmarks


def best_landmark(
    image_bytes: bytes, api_key: str
) -> Optional[LandmarkResult]:
    """Convenience helper: return the highest-confidence landmark, or None."""
    results = detect_landmarks(image_bytes, api_key, max_results=3)
    return results[0] if results else None
