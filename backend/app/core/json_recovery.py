"""Conservative recovery of a JSON object from conversational model output."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator


_FENCE = re.compile(r"```(?:json)?\s*|```", flags=re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _object_candidates(text: str) -> Iterator[str]:
    """Yield balanced-looking suffixes beginning at each object opener."""
    yield text
    for position, character in enumerate(text):
        if character == "{":
            yield text[position:]


def decode_json_object(raw: str) -> dict | None:
    """Return the first complete mapping without silently dropping nested data."""
    cleaned = _FENCE.sub("", raw).strip()
    decoder = json.JSONDecoder()
    for candidate in _object_candidates(cleaned):
        try:
            value, _remainder = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    without_trailing_commas = _TRAILING_COMMA.sub(r"\1", cleaned)
    try:
        value = json.loads(without_trailing_commas)
    except json.JSONDecodeError:
        try:
            value = ast.literal_eval(without_trailing_commas)
        except (SyntaxError, ValueError):
            return None
    return value if isinstance(value, dict) else None
