"""
CSV preprocessing utilities for the HIES column-classification pipeline.

Ported from hies/src/preprocess.py
"""

import re
import pandas as pd
from typing import Any, Dict, Tuple

from .config import COLUMN_NORMALIZE_PATTERNS


def normalize_column_name(col_name: str) -> str:
    """Lowercase, strip, and normalise a column name."""
    if pd.isna(col_name):
        return 'unnamed_column'
    normalized = str(col_name).lower().strip()
    for pattern, replacement in COLUMN_NORMALIZE_PATTERNS:
        normalized = pattern.sub(replacement, normalized)
    normalized = re.sub(r'_+', '_', normalized).strip('_')
    return normalized or 'unnamed_column'


def infer_dtype(series: pd.Series) -> str:
    """Infer a human-readable dtype for a pandas Series."""
    if series.isna().all():
        return 'all_null'
    try:
        pd.to_numeric(series.dropna(), errors='raise')
        if series.dropna().apply(lambda x: float(x).is_integer()).all():
            return 'integer'
        return 'float'
    except (ValueError, TypeError):
        pass
    try:
        pd.to_datetime(series.dropna(), errors='raise')
        return 'datetime'
    except (ValueError, TypeError):
        pass
    if series.dropna().isin([True, False, 'True', 'False', 'true', 'false', 1, 0, '1', '0']).all():
        return 'boolean'
    return 'string'


def compute_profiling_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute basic profiling statistics for every column in *df*."""
    stats = []
    for col in df.columns:
        series = df[col]
        missing_pct = (series.isna().sum() / len(series)) * 100
        n_unique = series.nunique()
        sample_values = series.dropna().unique()[:5].tolist()
        sample_str = ', '.join([str(v)[:50] for v in sample_values])
        stats.append({
            'original_name':   col,
            'normalized_name': normalize_column_name(col),
            'dtype':           infer_dtype(series),
            'missing_pct':     round(missing_pct, 2),
            'n_unique':        n_unique,
            'sample_values':   sample_str,
            'total_rows':      len(series),
        })
    return pd.DataFrame(stats)


def preprocess_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Normalise column names and compute profiling stats for a DataFrame.

    Returns:
        (df_normalized, profiling_df)
    """
    column_mapping = {col: normalize_column_name(col) for col in df.columns}
    df_normalized = df.rename(columns=column_mapping)
    profiling_df = compute_profiling_stats(df_normalized)
    return df_normalized, profiling_df


def preprocess_csv(
    file_path: str = None,
    uploaded_file=None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load and preprocess a CSV file.

    Args:
        file_path:     Path to CSV file (optional).
        uploaded_file: Uploaded file object (optional).

    Returns:
        Tuple of (preprocessed DataFrame, profiling statistics DataFrame).
    """
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
    elif file_path is not None:
        df = pd.read_csv(file_path)
    else:
        raise ValueError("Either file_path or uploaded_file must be provided")

    column_mapping = {col: normalize_column_name(col) for col in df.columns}
    df_normalized = df.rename(columns=column_mapping)
    # Profiling stats use original names to preserve readability
    profiling_df = compute_profiling_stats(df)
    return df_normalized, profiling_df


def get_column_summary(df: pd.DataFrame, col_name: str) -> Dict[str, Any]:
    """
    Return detailed statistics for a single column.

    Args:
        df:       DataFrame.
        col_name: Normalised column name.

    Returns:
        Dictionary with column statistics (empty dict if column not found).
    """
    if col_name not in df.columns:
        return {}

    series = df[col_name]

    summary: Dict[str, Any] = {
        'name':          col_name,
        'dtype':         infer_dtype(series),
        'missing_count': int(series.isna().sum()),
        'missing_pct':   round((series.isna().sum() / len(series)) * 100, 2),
        'n_unique':      int(series.nunique()),
        'n_total':       len(series),
        'sample_values': series.dropna().unique()[:10].tolist(),
    }

    if summary['dtype'] in ['integer', 'float']:
        numeric_series = pd.to_numeric(series.dropna(), errors='coerce')
        summary['min']  = float(numeric_series.min())  if len(numeric_series) > 0 else None
        summary['max']  = float(numeric_series.max())  if len(numeric_series) > 0 else None
        summary['mean'] = float(numeric_series.mean()) if len(numeric_series) > 0 else None
        summary['std']  = float(numeric_series.std())  if len(numeric_series) > 0 else None

    return summary
