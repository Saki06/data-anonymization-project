"""
Quasi-identifier and sensitive-attribute detection for the HIES pipeline.

Ported from hies/src/detect_qi_sensitive.py
"""

import re
import pandas as pd
from typing import Any, Dict, List, Tuple

from .config import (
    HIGH_PRIORITY_QUASI_IDENTIFIERS,
    HIGH_PRIORITY_SENSITIVE,
    QUASI_IDENTIFIER_KEYWORDS,
    SENSITIVE_KEYWORDS,
)


def _extract_semantic_features(
    column_name: str,
    series: pd.Series,
) -> Dict[str, Any]:
    """Extract semantic and statistical features from a column."""
    col_lower = column_name.lower()
    non_null = series.dropna()
    features: Dict[str, Any] = {
        'name_tokens':        set(re.findall(r'\w+', col_lower)),
        'name_length':        len(column_name),
        'word_count':         len(col_lower.split('_')),
        'has_numeric_suffix': bool(re.search(r'\d+$', col_lower)),
        'n_unique':           series.nunique(),
        'n_total':            len(series),
        'uniqueness_ratio':   series.nunique() / len(non_null) if len(non_null) > 0 else 0,
        'sample_values':      non_null.astype(str).head(10).tolist(),
    }
    # sample_text — first 5 values joined; reserved for future NLP use
    features['sample_text'] = ' '.join([str(v).lower() for v in features['sample_values'][:5]])
    try:
        numeric_series = pd.to_numeric(non_null, errors='coerce')
        if numeric_series.notna().sum() > 0:
            features['is_numeric']     = True
            features['numeric_range']  = float(numeric_series.max() - numeric_series.min())
            features['numeric_mean']   = float(numeric_series.mean())
        else:
            features['is_numeric'] = False
    except Exception:
        features['is_numeric'] = False
    return features


def _keyword_similarity_score(
    tokens: set,
    keyword_lists: Dict[str, List[str]],
) -> Dict[str, float]:
    """
    Compute a Jaccard-based similarity score between *tokens* and each
    keyword category in *keyword_lists*.
    """
    scores = {}
    for category, keywords in keyword_lists.items():
        cat_tokens: set = set()
        for keyword in keywords:
            cat_tokens.update(re.findall(r'\w+', keyword.lower()))
        intersection = tokens.intersection(cat_tokens)
        union = tokens.union(cat_tokens)
        jaccard = len(intersection) / len(union) if union else 0.0
        if any(kw in ' '.join(tokens) for kw in keywords):
            jaccard = min(1.0, jaccard + 0.3)
        scores[category] = jaccard
    return scores


def _classify_quasi_identifier(
    features: Dict[str, Any],
) -> Tuple[str, float, List[str]]:
    """Return (class, confidence, reasons) for quasi-identifier classification."""
    tokens = features['name_tokens']
    qi_scores = _keyword_similarity_score(tokens, QUASI_IDENTIFIER_KEYWORDS)
    best_cat, best_score = max(qi_scores.items(), key=lambda x: x[1]) if qi_scores else (None, 0.0)
    if best_score > 0.3:
        confidence = min(1.0, best_score * 1.2)
        reasons = [f"Matches {best_cat} quasi-identifier pattern"]
        if 0.1 < features['uniqueness_ratio'] < 0.9:
            reasons.append("Moderate uniqueness suggests QI")
            confidence = min(1.0, confidence + 0.1)
        if features['is_numeric'] and best_cat == 'age':
            reasons.append("Numeric values consistent with age")
            confidence = min(1.0, confidence + 0.15)
        return 'QUASI_IDENTIFIER', round(confidence, 3), reasons
    return 'NONE', 0.0, []


def _classify_sensitive_attribute(
    features: Dict[str, Any],
) -> Tuple[str, float, List[str]]:
    """Return (class, confidence, reasons) for sensitive-attribute classification."""
    tokens = features['name_tokens']
    sens_scores = _keyword_similarity_score(tokens, SENSITIVE_KEYWORDS)
    best_cat, best_score = max(sens_scores.items(), key=lambda x: x[1]) if sens_scores else (None, 0.0)
    if best_score > 0.25:
        confidence = min(1.0, best_score * 1.3)
        reasons = [f"Matches {best_cat} sensitive attribute pattern"]
        if best_cat == 'income' and features['is_numeric']:
            reasons.append("Numeric values consistent with income")
            confidence = min(1.0, confidence + 0.2)
        if best_cat in ['religion', 'ethnicity'] and 1 < features['n_unique'] < 50:
            reasons.append("Categorical values consistent with sensitive attribute")
            confidence = min(1.0, confidence + 0.15)
        return 'SENSITIVE', round(confidence, 3), reasons
    return 'NONE', 0.0, []


def detect_qi_and_sensitive(
    df: pd.DataFrame,
    profiling_df: pd.DataFrame,
    direct_identifier_cols: List[str] = None,
) -> pd.DataFrame:
    """
    Classify columns as QUASI_IDENTIFIER, SENSITIVE, or NON_SENSITIVE.

    Already-identified direct-identifier columns are skipped.

    Args:
        df:                    Normalised DataFrame.
        profiling_df:          Output of compute_profiling_stats().
        direct_identifier_cols: List of normalised column names already
                                classified as direct identifiers.

    Returns:
        DataFrame with one row per non-direct-identifier column.
    """
    if direct_identifier_cols is None:
        direct_identifier_cols = []
    results = []
    for _, profile_row in profiling_df.iterrows():
        col_name      = profile_row['normalized_name']
        original_name = profile_row['original_name']
        if col_name not in df.columns or col_name in direct_identifier_cols:
            continue

        series    = df[col_name]
        col_lower = col_name.lower()

        if col_lower in [n.lower() for n in HIGH_PRIORITY_QUASI_IDENTIFIERS]:
            classification, confidence = 'QUASI_IDENTIFIER', 1.0
            reasons  = ["High-priority dataset-specific quasi-identifier"]
            evidence = f"Exact match in HIGH_PRIORITY_QUASI_IDENTIFIERS: {col_lower}"
        elif col_lower in [n.lower() for n in HIGH_PRIORITY_SENSITIVE]:
            classification, confidence = 'SENSITIVE', 1.0
            reasons  = ["High-priority dataset-specific sensitive attribute"]
            evidence = f"Exact match in HIGH_PRIORITY_SENSITIVE: {col_lower}"
        else:
            features = _extract_semantic_features(col_name, series)
            qi_class,   qi_conf,   qi_reasons   = _classify_quasi_identifier(features)
            sens_class, sens_conf, sens_reasons  = _classify_sensitive_attribute(features)

            if qi_conf > sens_conf and qi_conf > 0.3:
                classification, confidence = qi_class, qi_conf
                reasons  = qi_reasons
                evidence = (f"Semantic features: {len(features['name_tokens'])} tokens, "
                            f"uniqueness={features['uniqueness_ratio']:.2%}")
            elif sens_conf > 0.25:
                classification, confidence = sens_class, sens_conf
                reasons  = sens_reasons
                evidence = (f"Semantic features: {len(features['name_tokens'])} tokens, "
                            f"n_unique={features['n_unique']}")
            else:
                classification, confidence = 'NON_SENSITIVE', 0.5
                reasons  = ["No strong signals for QI or sensitive classification"]
                evidence = "Low semantic similarity to known patterns"

        results.append({
            'column_name':     original_name,
            'normalized_name': col_name,
            'class':           classification,
            'confidence':      confidence,
            'reasons':         '; '.join(reasons) if reasons else 'N/A',
            'evidence':        evidence,
        })
    return pd.DataFrame(results)


def combine_classifications(
    direct_df: pd.DataFrame,
    qi_sensitive_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge direct-identifier and QI/sensitive classification DataFrames.

    Direct-identifier columns are removed from *qi_sensitive_df* before
    concatenating to avoid duplicates.
    """
    combined = qi_sensitive_df.copy()
    direct_cols = set(direct_df['normalized_name'].tolist())
    combined = combined[~combined['normalized_name'].isin(direct_cols)]
    combined = pd.concat([combined, direct_df], ignore_index=True)
    return combined.sort_values('column_name').reset_index(drop=True)
