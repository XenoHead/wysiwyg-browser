"""Walmart Marketplace API integration for WysiWyg.

The client lives in ``walmart_api``; the smoke-test CLI lives in ``cli``.
Nothing in this package is imported by ``main.py`` yet -- wiring is a separate
decision (see README.md, "Roadmap").
"""

from .walmart_api import WalmartAPI, WalmartAPIError  # noqa: F401

__all__ = ["WalmartAPI", "WalmartAPIError"]
