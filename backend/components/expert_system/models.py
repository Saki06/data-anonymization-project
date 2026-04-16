"""
Data models and types for the expert system
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable


@dataclass
class SDCMethod:
    """Represents a single Statistical Disclosure Control method."""
    key: str
    label: str
    description: str
    privacy_level: str  # Low, Medium, High, Very High
    utility_impact: str  # Low, Medium, High, Very High
    ai_feedback: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    applicable_to: List[str] = field(default_factory=list)  # categorical, numeric, datetime, geographic


@dataclass
class Rule:
    """Represents a rule in the expert system."""
    name: str
    conditions: List[Callable[[Dict[str, Any]], bool]]
    recommended_methods: List[str]
    explanation: str
    severity: str = "Medium"  # Low, Medium, High, Critical


@dataclass
class Recommendation:
    """Represents a single recommendation."""
    method: str
    details: str
    privacy_level: str
    utility_impact: str
    explanation: str
    ai_feedback: Optional[str] = None
    confidence: float = 1.0
    reason: str = ""


@dataclass
class RecommendationSet:
    """Set of recommendations for a dataset profile."""
    recommendations: List[Recommendation]
    primary_method: str
    secondary_methods: List[str]
    hybrid_approach: bool
    overall_privacy_level: str
    overall_utility_impact: str
    additional_notes: str = ""