from typing import Any


def to_int(element: Any) -> int | None:
    if element is None:
        return None
    try:
        return int(element)
    except (TypeError, ValueError):
        return None


def to_float(element: Any) -> float | None:
    if element is None:
        return None
    try:
        return float(element)
    except (TypeError, ValueError):
        return None


def get_value(dictionary: Any, keys: list) -> Any | None:
    """Walk a nested path into ``dictionary``; return None if any hop misses."""
    nested = dictionary
    for key in keys:
        try:
            nested = nested[key]
        except (KeyError, IndexError, TypeError):
            return None
    return nested
