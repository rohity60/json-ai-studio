"""NVIDIA NIM provider — GPU-accelerated inference API."""

from __future__ import annotations

from .base import DeploymentProvider


class NvidiaNimProvider(DeploymentProvider):
    name = "nvidia_nim"
    model_prefix = "nvidia/"
    api_key_setting = "nvidia_nim_api_key"
    default_base_url = "https://integrate.api.nvidia.com/v1"
    # No published per-token pricing wired yet; unknown models cost 0.0.
    PRICING: dict[str, tuple[float, float]] = {}
