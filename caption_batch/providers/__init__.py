from .base import CaptionRequest, Provider
from .gemini import GeminiProvider
from .openrouter import OpenRouterProvider

PROVIDERS = {
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
}


def get_provider(name: str, api_key: str | None = None) -> Provider:
    key = name.lower().strip()
    if key not in PROVIDERS:
        raise SystemExit(f"Unknown provider: {name}. Choose: {', '.join(PROVIDERS)}")
    return PROVIDERS[key](api_key=api_key)
