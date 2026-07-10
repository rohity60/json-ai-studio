"""Deployment providers (ADR-0016). One class per LLM backend.

PROVIDER_CLASSES maps deployments.yaml entry names to provider classes.
Adding a backend = new subclass file + one entry here + a yaml entry.
"""

from .base import DeploymentProvider
from .google_ai_studio import GoogleAIStudioProvider
from .nvidia_nim import NvidiaNimProvider
from .ollama import OllamaProvider
from .openrouter import OpenRouterProvider

PROVIDER_CLASSES: dict[str, type[DeploymentProvider]] = {
    cls.name: cls
    for cls in (
        GoogleAIStudioProvider,
        NvidiaNimProvider,
        OpenRouterProvider,
        OllamaProvider,
    )
}

__all__ = [
    "DeploymentProvider",
    "GoogleAIStudioProvider",
    "NvidiaNimProvider",
    "OllamaProvider",
    "OpenRouterProvider",
    "PROVIDER_CLASSES",
]
