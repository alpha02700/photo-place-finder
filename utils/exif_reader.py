"""
EXIF GPS extractor.

Reads GPS coordinates embedded in photo metadata (EXIF). Most smartphone
photos contain this automatically when location services are enabled.
"""
from __future__ import annotations

from typing import Optional, Tuple

from PIL import Image, ExifTags


# Pre-compute reverse lookups once.
_EXIF_TAGS = {v: k for k, v in ExifTags.TAGS.items()}
_GPS_TAGS = {v: k for k, v in ExifTags.GPSTAGS.items()}


def _to_degrees(value) -> float:
    """Convert EXIF GPS coordinate (rationals) to decimal degrees."""
    d, m, s = value
    # Pillow returns IFDRational, which supports float().
    return float(d) + float(m) / 60.0 + float(s) / 3600.0


def extract_gps(image: Image.Image) -> Optional[Tuple[float, float]]:
    """
    Extract (latitude, longitude) from a PIL Image's EXIF data.

    Returns None if no GPS tag is present (very common for screenshots,
    edited photos, or images stripped of metadata).
    """
    try:
        exif = image.getexif()
    except Exception:
        return None

    if not exif:
        return None

    # GPSInfo lives at tag 34853 in the main IFD.
    gps_ifd_tag = _EXIF_TAGS.get("GPSInfo")
    if gps_ifd_tag is None:
        return None

    gps_info = exif.get_ifd(gps_ifd_tag)
    if not gps_info:
        return None

    # Map numeric tag IDs to human-readable names.
    gps_data = {}
    for key, val in gps_info.items():
        name = ExifTags.GPSTAGS.get(key, key)
        gps_data[name] = val

    lat_values = gps_data.get("GPSLatitude")
    lat_ref = gps_data.get("GPSLatitudeRef")
    lon_values = gps_data.get("GPSLongitude")
    lon_ref = gps_data.get("GPSLongitudeRef")

    if not (lat_values and lon_values and lat_ref and lon_ref):
        return None

    try:
        lat = _to_degrees(lat_values)
        lon = _to_degrees(lon_values)
    except Exception:
        return None

    if isinstance(lat_ref, bytes):
        lat_ref = lat_ref.decode(errors="ignore")
    if isinstance(lon_ref, bytes):
        lon_ref = lon_ref.decode(errors="ignore")

    if lat_ref.upper() == "S":
        lat = -lat
    if lon_ref.upper() == "W":
        lon = -lon

    # Sanity check: latitude in [-90, 90], longitude in [-180, 180].
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None

    return lat, lon
