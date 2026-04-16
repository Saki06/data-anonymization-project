"""
Direct-identifier detection for the HIES column-classification pipeline.

Ported from hies/src/detect_direct.py
"""

import re
import pandas as pd
from typing import Dict, List, Tuple

from .config import (
    HIGH_PRIORITY_DIRECT_IDENTIFIERS,
    DIRECT_IDENTIFIER_KEYWORDS,
    DIRECT_IDENTIFIER_PATTERNS,
)


def _check_keyword_match(
    column_name: str,
    keywords: Dict[str, List[str]],
) -> Tuple[str, float]:
    """
    Check if *column_name* contains any known direct-identifier keyword.

    Returns:
        (category, confidence) or (None, 0.0)
    """
    col_lower = column_name.lower()
    for category, keyword_list in keywords.items():
        for keyword in keyword_list:
            if keyword in col_lower:
                if col_lower == keyword or re.search(r'\b' + re.escape(keyword) + r'\b', col_lower):
                    return category, 0.95
                return category, 0.75
    return None, 0.0


def _check_regex_pattern(
    series: pd.Series,
    patterns: Dict[str, re.Pattern],
) -> Tuple[str, float]:
    """
    Check how many values in *series* match known PII regex patterns.

    Returns:
        (best_matching_category, confidence) or (None, 0.0)
    """
    non_null = series.dropna().astype(str)
    if len(non_null) == 0:
        return None, 0.0
    best_match, best_confidence = None, 0.0
    for category, pattern in patterns.items():
        match_rate = (
            non_null.apply(lambda x: bool(pattern.search(str(x))) if pd.notna(x) else False).sum()
            / len(non_null)
        )
        if match_rate > 0.8:
            confidence = 0.9
        elif match_rate > 0.5:
            confidence = 0.7
        elif match_rate > 0.2:
            confidence = 0.5
        else:
            confidence = 0.0
        if confidence > best_confidence:
            best_confidence = confidence
            best_match = category
    return best_match, best_confidence


def _check_uniqueness(series: pd.Series) -> float:
    """Return the ratio of unique values to non-null values."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return 0.0
    return non_null.nunique() / len(non_null)


def detect_direct_identifiers(
    df: pd.DataFrame,
    profiling_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Scan every column in *df* for direct-identifier signals.

    Args:
        df:           Normalised DataFrame.
        profiling_df: Output of compute_profiling_stats().

    Returns:
        DataFrame of columns classified as DIRECT_IDENTIFIER.
    """
    results = []
    for _, profile_row in profiling_df.iterrows():
        col_name      = profile_row['normalized_name']
        original_name = profile_row['original_name']
        if col_name not in df.columns:
            continue

        series = df[col_name]
        classification, confidence, reasons, evidence = 'NONE', 0.0, [], []

        col_lower = col_name.lower()
        if col_lower in [n.lower() for n in HIGH_PRIORITY_DIRECT_IDENTIFIERS]:
            classification = 'DIRECT_IDENTIFIER'
            confidence = 1.0
            reasons.append("High-priority dataset-specific direct identifier")
            evidence.append(f"Exact match in HIGH_PRIORITY_DIRECT_IDENTIFIERS: {col_lower}")

        kw_cat, kw_conf = _check_keyword_match(col_name, DIRECT_IDENTIFIER_KEYWORDS)
        if kw_cat:
            classification = 'DIRECT_IDENTIFIER'
            confidence = max(confidence, kw_conf)
            reasons.append(f"Column name matches {kw_cat} keyword pattern")
            evidence.append(f"Keyword match: {kw_cat}")

        rx_cat, rx_conf = _check_regex_pattern(series, DIRECT_IDENTIFIER_PATTERNS)
        if rx_cat:
            classification = 'DIRECT_IDENTIFIER'
            confidence = max(confidence, rx_conf)
            reasons.append(f"Values match {rx_cat} pattern")
            evidence.append(f"Regex match: {rx_cat}")

        uniqueness = _check_uniqueness(series)
        if uniqueness > 0.95 and len(series.dropna()) > 10:
            if kw_cat or rx_cat:
                confidence = min(1.0, confidence + 0.1)
                reasons.append("Very high uniqueness (>95%)")
                evidence.append(f"Uniqueness: {uniqueness:.2%}")
            elif 'id' in col_lower:
                classification = 'DIRECT_IDENTIFIER'
                confidence = 0.8
                reasons.append("High uniqueness (>95%) and 'id' in column name")
                evidence.append(f"Uniqueness: {uniqueness:.2%}")

        if classification == 'DIRECT_IDENTIFIER':
            results.append({
                'column_name':     original_name,
                'normalized_name': col_name,
                'class':           classification,
                'confidence':      round(confidence, 3),
                'reasons':         '; '.join(reasons) or 'Rule-based detection',
                'evidence':        '; '.join(evidence) or 'N/A',
            })
    return pd.DataFrame(results)
