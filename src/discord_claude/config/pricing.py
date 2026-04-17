"""Load Claude model pricing and context-window metadata from pricing.yaml.

The YAML file ships with the package so pricing is always available. Set the
``CLAUDE_PRICING_PATH`` environment variable to point at a different YAML file
for runtime overrides (e.g. when a vendor price change beats the next release).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict

import yaml


class _UnknownFallback(TypedDict):
    input_per_million: float
    output_per_million: float


def _resolve_pricing_path() -> Path:
    override = os.getenv("CLAUDE_PRICING_PATH")
    if override:
        return Path(override)
    return Path(__file__).with_name("pricing.yaml")


def _load_raw() -> dict[str, Any]:
    path = _resolve_pricing_path()
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a YAML mapping at the top level.")
    return data


_RAW: dict[str, Any] = _load_raw()
_MODELS: dict[str, dict[str, Any]] = _RAW.get("models") or {}
_TOOLS: dict[str, dict[str, Any]] = _RAW.get("tools") or {}
_FALLBACK: _UnknownFallback = _RAW.get("unknown_model_fallback") or {
    "input_per_million": 15.0,
    "output_per_million": 75.0,
}

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    model_id: int(cfg["context_window"])
    for model_id, cfg in _MODELS.items()
    if "context_window" in cfg
}

MODEL_PRICING: dict[str, tuple[float, float]] = {
    model_id: (float(cfg["input_per_million"]), float(cfg["output_per_million"]))
    for model_id, cfg in _MODELS.items()
    if "input_per_million" in cfg and "output_per_million" in cfg
}

UNKNOWN_MODEL_PRICING: tuple[float, float] = (
    float(_FALLBACK["input_per_million"]),
    float(_FALLBACK["output_per_million"]),
)

WEB_SEARCH_COST_PER_REQUEST: float = float(_TOOLS.get("web_search", {}).get("per_request", 0.01))

__all__ = [
    "MODEL_CONTEXT_WINDOWS",
    "MODEL_PRICING",
    "UNKNOWN_MODEL_PRICING",
    "WEB_SEARCH_COST_PER_REQUEST",
]
