from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnthropicMcpPreset:
    """Validated Anthropic MCP preset loaded from env or JSON config."""

    name: str
    server_url: str
    authorization_env_var: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    defer_loading: bool = False
    available: bool = True
    unavailable_reason: str | None = None


def _load_json_object(raw_value: str, source_name: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{source_name} must contain valid JSON.") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{source_name} must be a JSON object keyed by preset name.")
    return parsed


def _validate_https_url(url: object, preset_name: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"MCP preset `{preset_name}` requires a non-empty `url`.")
    normalized = url.strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.hostname:
        raise ValueError(f"MCP preset `{preset_name}` must use a valid HTTPS `url`.")
    return normalized


def _validate_allowed_tools(value: object, preset_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"MCP preset `{preset_name}` `allowed_tools` must be a list of strings.")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _validate_preset(name: str, raw_value: object) -> AnthropicMcpPreset:
    if not isinstance(raw_value, dict):
        raise ValueError(f"MCP preset `{name}` must be an object.")

    supported_keys = {"url", "authorization_env_var", "allowed_tools", "defer_loading"}
    extra_keys = sorted(set(raw_value) - supported_keys)
    if extra_keys:
        raise ValueError(
            f"MCP preset `{name}` contains unsupported keys: {', '.join(extra_keys)}."
        )

    authorization_env_var = raw_value.get("authorization_env_var")
    if authorization_env_var is not None and not isinstance(authorization_env_var, str):
        raise ValueError(f"MCP preset `{name}` `authorization_env_var` must be a string.")

    defer_loading = raw_value.get("defer_loading", False)
    if not isinstance(defer_loading, bool):
        raise ValueError(f"MCP preset `{name}` `defer_loading` must be a boolean.")

    preset = AnthropicMcpPreset(
        name=name,
        server_url=_validate_https_url(raw_value.get("url"), name),
        authorization_env_var=authorization_env_var,
        allowed_tools=_validate_allowed_tools(raw_value.get("allowed_tools"), name),
        defer_loading=defer_loading,
    )

    if preset.authorization_env_var and not os.getenv(preset.authorization_env_var):
        LOGGER.warning(
            "Anthropic MCP preset `%s` is unavailable because `%s` is not set.",
            name,
            preset.authorization_env_var,
        )
        return AnthropicMcpPreset(
            name=preset.name,
            server_url=preset.server_url,
            authorization_env_var=preset.authorization_env_var,
            allowed_tools=preset.allowed_tools,
            defer_loading=preset.defer_loading,
            available=False,
            unavailable_reason=(
                f"MCP preset `{name}` requires the `{preset.authorization_env_var}` env var."
            ),
        )

    return preset


def load_anthropic_mcp_presets() -> dict[str, AnthropicMcpPreset]:
    """Load Anthropic MCP presets from JSON env text and/or a JSON file path."""
    merged: dict[str, object] = {}

    inline_json = os.getenv("ANTHROPIC_MCP_PRESETS_JSON", "").strip()
    if inline_json:
        merged.update(_load_json_object(inline_json, "ANTHROPIC_MCP_PRESETS_JSON"))

    presets_path = os.getenv("ANTHROPIC_MCP_PRESETS_PATH", "").strip()
    if presets_path:
        file_data = Path(presets_path).read_text(encoding="utf-8")
        path_presets = _load_json_object(file_data, "ANTHROPIC_MCP_PRESETS_PATH")
        duplicate_names = sorted(set(merged) & set(path_presets))
        if duplicate_names:
            raise ValueError(
                "Duplicate Anthropic MCP preset names found across env and file config: "
                + ", ".join(duplicate_names)
            )
        merged.update(path_presets)

    presets: dict[str, AnthropicMcpPreset] = {}
    for name, raw_value in merged.items():
        presets[name] = _validate_preset(name, raw_value)
    return presets


ANTHROPIC_MCP_PRESETS = load_anthropic_mcp_presets()


def parse_mcp_preset_names(raw_value: str | None) -> list[str]:
    """Parse a comma-separated list of preset names from Discord command input."""
    if raw_value is None:
        return []
    parsed_names: list[str] = []
    seen: set[str] = set()
    for piece in raw_value.split(","):
        name = piece.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        parsed_names.append(name)
    return parsed_names


def resolve_mcp_presets(
    preset_names: list[str],
) -> tuple[list[AnthropicMcpPreset], str | None]:
    """Resolve preset names to validated Anthropic MCP presets."""
    presets: list[AnthropicMcpPreset] = []
    for name in preset_names:
        preset = ANTHROPIC_MCP_PRESETS.get(name)
        if preset is None:
            return [], f"Unknown MCP preset `{name}`."
        if not preset.available:
            return [], preset.unavailable_reason or f"MCP preset `{name}` is unavailable."
        presets.append(preset)
    return presets, None


__all__ = [
    "ANTHROPIC_MCP_PRESETS",
    "AnthropicMcpPreset",
    "load_anthropic_mcp_presets",
    "parse_mcp_preset_names",
    "resolve_mcp_presets",
]
