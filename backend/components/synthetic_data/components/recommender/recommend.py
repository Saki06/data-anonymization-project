"""
Recommendation engine for Component 02.

Defines the `Recommendation` dataclass and the `recommend_pipeline`
function that chooses between:
- synthetic
- anonymize
- hybrid

This module uses heuristics inspired by `Member 02/model 02`'s
RiskAnalyzer and knowledge base but is simplified for integration
with the FastAPI backend.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import pandas as pd

from ..identification import DatasetMetadata
from .rules import estimate_uniqueness_risk, has_direct_identifiers, summarize_risk_level


@dataclass
class Recommendation:
    """Container for SDC strategy recommendations."""

    chosen_strategy: str  # "synthetic" | "anonymize" | "hybrid"
    selected_methods: List[Dict[str, Any]]
    epsilon: Optional[float]
    epsilon_allocation: Optional[Dict[str, float]]
    rationale: str
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _default_epsilon(metadata: DatasetMetadata) -> float:
    """
    Pick a reasonable default epsilon based on basic properties.
    """
    n_cols = len(metadata.columns)
    if n_cols > 40:
        return 1.0
    if n_cols > 20:
        return 0.8
    return 0.6


def recommend_pipeline(
    df: pd.DataFrame,
    metadata: DatasetMetadata,
    user_goal: str,
    preference: Optional[str] = None,
) -> Recommendation:
    """
    Decide which SDC pipeline to use and which methods to configure.

    Args:
        df: Original dataframe.
        metadata: DatasetMetadata from Component 01.
        user_goal: Free-text goal, e.g., "research", "publication".
        preference: Optional user preference: "synthetic" | "anonymize" | "hybrid".

    Returns:
        Recommendation object.
    """
    warnings: List[str] = []

    uniq_risk = estimate_uniqueness_risk(df, metadata)
    risk_level = summarize_risk_level(uniq_risk)
    has_ids = has_direct_identifiers(metadata)

    epsilon = _default_epsilon(metadata)

    if has_ids or risk_level == "high":
        strategy = "synthetic"
        rationale = (
            "Direct identifiers or very high uniqueness risk detected; "
            "defaulting to full synthetic data generation using APEDP."
        )
    elif risk_level == "medium":
        if preference == "anonymize":
            strategy = "anonymize"
            rationale = (
                "Medium re-identification risk; user preference is anonymization, "
                "so k-anonymity style methods will be applied."
            )
        elif preference == "hybrid":
            strategy = "hybrid"
            rationale = (
                "Medium risk with hybrid preference; direct identifiers will be anonymized or dropped "
                "and APEDP synthetic data used for remaining variables."
            )
        else:
            strategy = "synthetic"
            rationale = (
                "Medium risk without strong user preference; leaning towards synthetic data "
                "for stronger privacy while preserving utility."
            )
    else:  # low risk
        if preference in {"anonymize", "hybrid"}:
            strategy = preference
            rationale = (
                f"Low risk but user requested '{preference}' strategy; applying requested pipeline."
            )
        else:
            strategy = "anonymize"
            rationale = (
                "Low overall risk; anonymization (k-anonymity, suppression, generalization) "
                "is sufficient and preserves more structure than fully synthetic data."
            )

    selected_methods: List[Dict[str, Any]] = []

    if strategy == "anonymize":
        selected_methods.append(
            {
                "method": "k_anonymity",
                "params": {"k": 5, "quasi_identifiers": metadata.quasi_identifiers},
            }
        )
        selected_methods.append(
            {
                "method": "suppression",
                "params": {"threshold": 5, "quasi_identifiers": metadata.quasi_identifiers},
            }
        )
    elif strategy == "synthetic":
        selected_methods.append(
            {
                "method": "apedp_synthetic",
                "params": {
                    "global_epsilon": epsilon,
                    "strata_keys": metadata.strata_candidates[:2],
                },
            }
        )
    elif strategy == "hybrid":
        selected_methods.append(
            {
                "method": "drop_direct_identifiers",
                "params": {"columns": metadata.direct_identifiers},
            }
        )
        selected_methods.append(
            {
                "method": "k_anonymity",
                "params": {"k": 5, "quasi_identifiers": metadata.quasi_identifiers},
            }
        )
        selected_methods.append(
            {
                "method": "apedp_synthetic",
                "params": {
                    "global_epsilon": epsilon,
                    "strata_keys": metadata.strata_candidates[:2],
                },
            }
        )

    epsilon_allocation: Optional[Dict[str, float]] = None

    if not metadata.quasi_identifiers:
        warnings.append(
            "No quasi-identifiers detected; some risk and anonymization analyses may be limited."
        )

    return Recommendation(
        chosen_strategy=strategy,
        selected_methods=selected_methods,
        epsilon=epsilon if strategy in {"synthetic", "hybrid"} else None,
        epsilon_allocation=epsilon_allocation,
        rationale=rationale,
        warnings=warnings,
    )
