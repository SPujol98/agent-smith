import os
from typing import Any, Dict, List
from dotenv import load_dotenv

load_dotenv()


def _parse_keys(env_var_name: str) -> List[str]:
    """Helper function to parse comma-separated API keys safely."""
    raw_value = os.getenv(env_var_name, "")
    keys: List[str] = []
    for key in raw_value.split(","):
        cleaned = key.strip()
        if cleaned:
            keys.append(cleaned)
    return keys


def get_providers_config() -> List[Dict[str, Any]]:
    """Reads multiple comma-separated API keys from the .env file for
    OpenRouter, Google Gemini, Groq, and OpenAI, returning structured
    providers with URLs, keys, and default models.
    """

    openrouter_keys = _parse_keys("OPENROUTER_API_KEYS")
    gemini_keys = _parse_keys("GOOGLE_GEMINI_KEYS")
    groq_keys = _parse_keys("GROQ_API_KEYS")
    openai_keys = _parse_keys("OPENAI_API_KEY")

    providers_config: List[Dict[str, Any]] = []

    if openrouter_keys:
        providers_config.append({
            "url": "https://openrouter.ai/api/v1",
            "keys": openrouter_keys,
            "default_model": "deepseek/deepseek-chat",
        })

    if groq_keys:
        providers_config.append({
            "url": "https://api.groq.com/openai/v1",
            "keys": groq_keys,
            "default_model": "llama-3.3-70b-versatile",
        })

    if gemini_keys:
        providers_config.append({
            "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "keys": gemini_keys,
            "default_model": "gemini-2.5-flash",
        })

    if openai_keys:
        providers_config.append({
            "url": "https://api.openai.com/v1",
            "keys": openai_keys,
            "default_model": "gpt-6-luna",
        })

    return providers_config


def get_default_model(provider_index: int = 0) -> str:
    """Gets the default model for a specific provider config index,

    falling back to a safe standard model if none are configured.
    """
    config = get_providers_config()
    if config and len(config) > provider_index:
        return config[provider_index].get("default_model", "gpt-6-luna")
    return "gpt-6-luna"
