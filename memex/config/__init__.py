"""Canonical configuration loaders for MEMEX.

All constants, weights, thresholds, and registries are loaded exclusively
from the addenda TOML files. No value from any addendum may be hard-coded
in any other source file.
"""

from .settings import get_settings, Settings

__all__ = ["get_settings", "Settings"]
