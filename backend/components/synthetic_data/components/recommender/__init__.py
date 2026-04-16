"""
Component 02: Recommendation Engine
"""

from .recommend import Recommendation, recommend_pipeline
from .rules import estimate_uniqueness_risk, has_direct_identifiers, summarize_risk_level

__all__ = [
    "Recommendation",
    "recommend_pipeline",
    "estimate_uniqueness_risk",
    "has_direct_identifiers",
    "summarize_risk_level",
]
