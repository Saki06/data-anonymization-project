"""
Heuristic and rule helpers for the Component 02 recommender.

This module borrows concepts from `Member 02/model 02`'s expert system
but exposes simpler utilities for deciding between synthetic,
anonymize, and hybrid strategies.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from ..identification import DatasetMetadata


def estimate_uniqueness_risk(df: pd.DataFrame, metadata: DatasetMetadata) -> float:
    """
    Estimate dataset-level uniqueness risk based on quasi identifiers.

    Returns a score in [0, 1].
    """
    qis = metadata.quasi_identifiers
    if not qis:
        return 0.2

    qi_df = df[qis].copy()
    if qi_df.empty:
        return 0.0

    combo_counts = qi_df.groupby(qis).size()
    unique_combos = (combo_counts == 1).sum()
    risk = unique_combos / max(len(qi_df), 1)
    return float(min(1.0, max(0.0, risk)))


def has_direct_identifiers(metadata: DatasetMetadata) -> bool:
    """True if any direct identifiers are present."""
    return len(metadata.direct_identifiers) > 0


def summarize_risk_level(uniqueness_risk: float) -> str:
    """Bucket numerical risk into 'low', 'medium', 'high'."""
    if uniqueness_risk >= 0.6:
        return "high"
    if uniqueness_risk >= 0.3:
        return "medium"
    return "low"
