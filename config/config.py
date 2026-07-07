"""
MarketHunter

config/config.py
"""

from __future__ import annotations

from config.loader import ConfigLoader
from config.validator import (
    ConfigValidator,
)


_loader = ConfigLoader()

_settings = _loader.load()

ConfigValidator().validate(
    _settings,
)


settings = _settings