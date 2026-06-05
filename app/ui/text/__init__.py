from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

_TEXT_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def _load_catalog(locale: str = "tr") -> dict[str, Any]:
    path = _TEXT_DIR / f"{locale}.json"
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"UI text catalog must be an object: {path}")
    return data


def build_ui_text_bundle(*sections: str, locale: str = "tr") -> dict[str, Any]:
    catalog = _load_catalog(locale)
    if not sections:
        return deepcopy(catalog)
    return {section: deepcopy(catalog[section]) for section in sections}


def get_ui_text(path: str, *, locale: str = "tr", **params: object) -> str:
    value: Any = _load_catalog(locale)
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(f"Unknown UI text path: {path}")
        value = value[part]
    if not isinstance(value, str):
        raise TypeError(f"UI text path does not resolve to a string: {path}")
    if params:
        return value.format(**params)
    return value
