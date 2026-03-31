import importlib
import warnings


def test_anthropic_api_shim_warns_and_reexports():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module = importlib.import_module("anthropic_api")

    assert module.ClaudeCog.__name__ == "ClaudeCog"
    assert not hasattr(module, "AnthropicAPI")
    assert any(item.category is DeprecationWarning for item in caught)
