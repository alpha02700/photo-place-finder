"""
Claude Vision fallback for landmark/building recognition.

When Google Vision API cannot identify a landmark, this module sends the
image to Claude (claude-haiku-4-5) and asks it to name the building plus
estimate its country/city.  The caller then uses Google Geocoding to turn
that description into precise coordinates.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Optional

import anthropic


@dataclass
class ClaudeLocationGuess:
    """Result returned by Claude vision analysis."""
    building_name: str       # e.g. "경복궁 (Gyeongbokgung Palace)"
    city_hint: str           # e.g. "서울, 대한민국"
    search_query: str        # ready-to-geocode string, e.g. "경복궁 서울"
    confidence: str          # "high" | "medium" | "low"
    description: str         # Claude's free-text explanation (shown in UI)


_SYSTEM_PROMPT = """You are an expert building and landmark recognition assistant.
Analyze the photo and identify the building or landmark shown.
Reply ONLY with a JSON object (no markdown fences) with these exact keys:
- "building_name": the name of the building/place in the local language + English if different
- "city_hint": city and country where it is located
- "search_query": a short geocodable string (name + city) to look it up on a map
- "confidence": "high", "medium", or "low"
- "description": one sentence describing what you see and why you identified it this way

If you genuinely cannot identify the location at all, set confidence to "low" and
provide your best guess anyway — never leave fields empty."""


def identify_building(
    image_bytes: bytes,
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
    timeout: int = 30,
) -> Optional[ClaudeLocationGuess]:
    """
    Ask Claude to identify a building/landmark from image bytes.

    Returns ClaudeLocationGuess or None on failure.
    """
    if not api_key:
        raise ValueError("Anthropic API key is required.")

    client = anthropic.Anthropic(api_key=api_key)

    # Detect media type (JPEG vs PNG).
    if image_bytes[:2] == b"\xff\xd8":
        media_type = "image/jpeg"
    elif image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        media_type = "image/png"
    else:
        media_type = "image/jpeg"  # safe fallback

    encoded = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        message = client.messages.create(
            model=model,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": encoded,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Please identify this building or landmark.",
                        },
                    ],
                }
            ],
            timeout=timeout,
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Claude API error: {e}") from e

    raw = message.content[0].text.strip()

    # Strip markdown code fences if Claude added them despite instructions.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    import json
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    return ClaudeLocationGuess(
        building_name=data.get("building_name", "Unknown"),
        city_hint=data.get("city_hint", ""),
        search_query=data.get("search_query", data.get("building_name", "")),
        confidence=data.get("confidence", "low"),
        description=data.get("description", ""),
    )
