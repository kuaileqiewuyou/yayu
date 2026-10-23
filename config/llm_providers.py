"""Stable provider IDs and compatibility with older settings files."""

PRESET_LLM_PROVIDERS = frozenset({"deepseek", "openai", "claude"})
CUSTOM_LLM_PROVIDER = "custom"
_CUSTOM_ALIASES = frozenset({"custom", "自定义", "openai_compatible", "aipaibox"})


def normalize_llm_provider(provider: str) -> str:
    value = provider.strip()
    lowered = value.lower()
    if lowered in _CUSTOM_ALIASES:
        return CUSTOM_LLM_PROVIDER
    if lowered in PRESET_LLM_PROVIDERS:
        return lowered
    return value


def llm_provider_choice(provider: str) -> str:
    """Unknown legacy services are edited through the custom endpoint form."""
    normalized = normalize_llm_provider(provider)
    return normalized if normalized in PRESET_LLM_PROVIDERS else CUSTOM_LLM_PROVIDER


def provider_setting(values: dict[str, str], provider: str) -> str:
    """Prefer the exact saved key, then accept case and legacy aliases."""
    if provider in values:
        return values[provider]
    normalized = normalize_llm_provider(provider)
    for key, value in values.items():
        if normalize_llm_provider(key) == normalized:
            return value
    return ""
