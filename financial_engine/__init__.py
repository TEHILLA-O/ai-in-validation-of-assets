"""Deterministic financial calculation engine.

Language models are not used here. Every valuation figure is produced by the
functions exported from this package.
"""

from financial_engine.engine import run_model
from financial_engine.lines import ENGINE_VERSION

__all__ = ["run_model", "ENGINE_VERSION"]
