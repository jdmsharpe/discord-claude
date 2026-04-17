"""Tests for the YAML-backed pricing loader."""

import importlib
import sys
import textwrap
from pathlib import Path


def _reload_pricing():
    """Force a fresh import of the loader to re-read whatever file it resolves."""
    for mod_name in ("discord_claude.config.pricing",):
        sys.modules.pop(mod_name, None)
    return importlib.import_module("discord_claude.config.pricing")


class TestPricingLoader:
    def test_bundled_yaml_populates_model_pricing(self):
        pricing = _reload_pricing()
        assert ("claude-opus-4-7") in pricing.MODEL_PRICING
        assert pricing.MODEL_PRICING["claude-opus-4-7"] == (5.0, 25.0)
        assert pricing.MODEL_PRICING["claude-haiku-4-5"] == (1.0, 5.0)

    def test_bundled_yaml_populates_context_windows(self):
        pricing = _reload_pricing()
        assert pricing.MODEL_CONTEXT_WINDOWS["claude-opus-4-7"] == 1_000_000
        assert pricing.MODEL_CONTEXT_WINDOWS["claude-haiku-4-5"] == 200_000

    def test_web_search_cost_loaded(self):
        pricing = _reload_pricing()
        assert pricing.WEB_SEARCH_COST_PER_REQUEST == 0.01

    def test_unknown_model_fallback_defaults(self):
        pricing = _reload_pricing()
        assert pricing.UNKNOWN_MODEL_PRICING == (15.0, 75.0)

    def test_env_var_override_path(self, monkeypatch, tmp_path: Path):
        """CLAUDE_PRICING_PATH should redirect the loader to a different YAML file."""
        custom_yaml = tmp_path / "custom-pricing.yaml"
        custom_yaml.write_text(
            textwrap.dedent(
                """
                models:
                  claude-fictional-7:
                    context_window: 500000
                    input_per_million: 7.5
                    output_per_million: 37.5
                tools:
                  web_search:
                    per_request: 0.05
                unknown_model_fallback:
                  input_per_million: 99.0
                  output_per_million: 999.0
                """
            ).strip()
        )
        monkeypatch.setenv("CLAUDE_PRICING_PATH", str(custom_yaml))

        pricing = _reload_pricing()

        assert pricing.MODEL_PRICING == {"claude-fictional-7": (7.5, 37.5)}
        assert pricing.MODEL_CONTEXT_WINDOWS == {"claude-fictional-7": 500_000}
        assert pricing.WEB_SEARCH_COST_PER_REQUEST == 0.05
        assert pricing.UNKNOWN_MODEL_PRICING == (99.0, 999.0)

    def test_calculate_cost_uses_fallback_for_unknown_model(self, monkeypatch, tmp_path: Path):
        """calculate_cost() should honor the YAML-configured fallback for unknown models."""
        custom_yaml = tmp_path / "custom-pricing.yaml"
        custom_yaml.write_text(
            textwrap.dedent(
                """
                models: {}
                unknown_model_fallback:
                  input_per_million: 42.0
                  output_per_million: 100.0
                """
            ).strip()
        )
        monkeypatch.setenv("CLAUDE_PRICING_PATH", str(custom_yaml))
        _reload_pricing()
        sys.modules.pop("discord_claude.util", None)
        util = importlib.import_module("discord_claude.util")

        # 1M input + 1M output under the override should equal $42 + $100 = $142.
        cost = util.calculate_cost("nonexistent-model", 1_000_000, 1_000_000)
        assert cost == 142.0
