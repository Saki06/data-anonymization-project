"""
Risk validation module for k-anonymity and privacy risk assessment.

Computes k-anonymity, uniqueness metrics, and identifies risky equivalence classes.

Ported from hies/src/risk_validation.py
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Any


def compute_equivalence_classes(
    df: pd.DataFrame,
    qi_columns: List[str],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute equivalence classes based on quasi-identifier columns.

    An equivalence class is a group of records that share the same
    values for all quasi-identifier columns.

    Args:
        df:         DataFrame to analyse.
        qi_columns: List of quasi-identifier column names (normalised).

    Returns:
        Tuple of (dataframe with class assignments, class sizes dataframe).
    """
    if not qi_columns:
        return pd.DataFrame(), pd.DataFrame()

    valid_qi_cols = [col for col in qi_columns if col in df.columns]

    if not valid_qi_cols:
        return pd.DataFrame(), pd.DataFrame()

    grouped = df.groupby(valid_qi_cols, dropna=False)
    class_sizes = grouped.size().reset_index(name='class_size')
    class_sizes['equivalence_class'] = range(len(class_sizes))

    df_with_class = df.merge(
        class_sizes[valid_qi_cols + ['equivalence_class', 'class_size']],
        on=valid_qi_cols,
        how='left',
    )

    return df_with_class, class_sizes


def compute_k_anonymity(
    df: pd.DataFrame,
    qi_columns: List[str],
) -> Dict[str, Any]:
    """
    Compute k-anonymity metric.

    k-anonymity is the minimum size of any equivalence class.
    A dataset is k-anonymous if every record is indistinguishable
    from at least k-1 other records with respect to the QI.

    Args:
        df:         DataFrame to analyse.
        qi_columns: List of quasi-identifier column names.

    Returns:
        Dictionary with k-anonymity metrics.
    """
    empty = {
        'k_anonymity':       0,
        'min_class_size':    0,
        'max_class_size':    0,
        'mean_class_size':   0,
        'median_class_size': 0,
        'total_classes':     0,
        'unique_records':    0,
        'unique_pct':        0.0,
    }

    if not qi_columns:
        return empty

    _, class_sizes = compute_equivalence_classes(df, qi_columns)

    if len(class_sizes) == 0:
        return empty

    sizes = class_sizes['class_size'].values
    unique_count  = int((sizes == 1).sum())
    total_records = int(sizes.sum())

    return {
        'k_anonymity':       int(sizes.min()),
        'min_class_size':    int(sizes.min()),
        'max_class_size':    int(sizes.max()),
        'mean_class_size':   float(sizes.mean()),
        'median_class_size': float(np.median(sizes)),
        'total_classes':     int(len(class_sizes)),
        'unique_records':    unique_count,
        'unique_pct':        round((unique_count / total_records) * 100, 2) if total_records > 0 else 0.0,
    }


def get_riskiest_classes(
    df: pd.DataFrame,
    qi_columns: List[str],
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Get the *top_n* riskiest (smallest) equivalence classes.

    Args:
        df:         DataFrame to analyse.
        qi_columns: List of quasi-identifier column names.
        top_n:      Number of riskiest classes to return.

    Returns:
        DataFrame with riskiest equivalence classes and their risk levels.
    """
    if not qi_columns:
        return pd.DataFrame()

    _, class_sizes = compute_equivalence_classes(df, qi_columns)

    if len(class_sizes) == 0:
        return pd.DataFrame()

    riskiest = class_sizes.nsmallest(top_n, 'class_size').copy()

    def assign_risk_level(size: int) -> str:
        if size == 1:
            return 'CRITICAL'
        elif size < 3:
            return 'HIGH'
        elif size < 5:
            return 'MEDIUM'
        return 'LOW'

    riskiest['risk_level'] = riskiest['class_size'].apply(assign_risk_level)

    cols = ['risk_level', 'class_size'] + [
        c for c in riskiest.columns
        if c not in ('risk_level', 'class_size', 'equivalence_class')
    ]
    if 'equivalence_class' in riskiest.columns:
        cols.append('equivalence_class')

    return riskiest[cols].reset_index(drop=True)


def validate_risk(
    df: pd.DataFrame,
    qi_columns: List[str],
) -> Dict[str, Any]:
    """
    Comprehensive risk validation for selected QI columns.

    Args:
        df:         DataFrame to analyse.
        qi_columns: List of quasi-identifier column names.

    Returns::

        {
          "risk_level":        "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNDEFINED",
          "risk_description":  "...",
          "k_anonymity_metrics": { k_anonymity, min/max/mean/median_class_size,
                                   total_classes, unique_records, unique_pct },
          "riskiest_classes":  [ { risk_level, class_size, ...qi_values } ],
          "qi_columns":        [...]
        }
    """
    k_anon_metrics  = compute_k_anonymity(df, qi_columns)
    riskiest_df     = get_riskiest_classes(df, qi_columns, top_n=10)

    k          = k_anon_metrics['k_anonymity']
    unique_pct = k_anon_metrics['unique_pct']

    if k == 0:
        risk_level       = 'UNDEFINED'
        risk_description = 'No QI columns selected or no valid equivalence classes'
    elif k == 1:
        risk_level       = 'CRITICAL'
        risk_description = f'Dataset is 1-anonymous: {unique_pct:.1f}% of records are unique'
    elif k < 3:
        risk_level       = 'HIGH'
        risk_description = f'Dataset is {k}-anonymous: High re-identification risk'
    elif k < 5:
        risk_level       = 'MEDIUM'
        risk_description = f'Dataset is {k}-anonymous: Moderate re-identification risk'
    else:
        risk_level       = 'LOW'
        risk_description = f'Dataset is {k}-anonymous: Lower re-identification risk'

    # Serialise the DataFrame to a list of plain dicts
    riskiest_list: List[Dict] = []
    if not riskiest_df.empty:
        for _, row in riskiest_df.iterrows():
            riskiest_list.append({
                str(col): (
                    int(v)   if isinstance(v, np.integer)  else
                    float(v) if isinstance(v, np.floating) else v
                )
                for col, v in row.items()
            })

    return {
        'risk_level':        risk_level,
        'risk_description':  risk_description,
        'k_anonymity_metrics': k_anon_metrics,
        'riskiest_classes':  riskiest_list,
        'qi_columns':        qi_columns,
    }


import numpy as np
import pandas as pd
from typing import Any, Dict, List, Tuple


def compute_equivalence_classes(
    df: pd.DataFrame,
    qi_columns: List[str],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Group rows by the combination of quasi-identifier values.

    Args:
        df:         DataFrame to analyse.
        qi_columns: List of quasi-identifier column names.

    Returns:
        (df, sizes_df) where sizes_df has columns
        [qi_combo_columns..., 'count', 'risk_percent']
    """
    if not qi_columns:
        empty = pd.DataFrame(columns=['count', 'risk_percent'])
        return df, empty

    valid_cols = [c for c in qi_columns if c in df.columns]
    if not valid_cols:
        empty = pd.DataFrame(columns=['count', 'risk_percent'])
        return df, empty

    grouped = df.groupby(valid_cols, dropna=False).size().reset_index(name='count')
    grouped['risk_percent'] = (grouped['count'] / len(df) * 100).round(2)
    return df, grouped


def compute_k_anonymity(
    df: pd.DataFrame,
    qi_columns: List[str],
) -> Dict[str, Any]:
    """
    Compute the k-anonymity value for *df* given *qi_columns*.

    k-anonymity = minimum equivalence-class size.
    A value of 1 means at least one record is unique → high re-id risk.

    Returns:
        Dict with keys: k_value, total_records, total_eq_classes,
        singleton_classes, singleton_records, risk_level.
    """
    if not qi_columns:
        return {
            'k_value':           int(len(df)),
            'total_records':     int(len(df)),
            'total_eq_classes':  1,
            'singleton_classes': 0,
            'singleton_records': 0,
            'risk_level':        'LOW',
        }

    _, grouped = compute_equivalence_classes(df, qi_columns)

    if grouped.empty:
        return {
            'k_value':           int(len(df)),
            'total_records':     int(len(df)),
            'total_eq_classes':  1,
            'singleton_classes': 0,
            'singleton_records': 0,
            'risk_level':        'LOW',
        }

    k_value           = int(grouped['count'].min())
    singleton_classes = int((grouped['count'] == 1).sum())
    singleton_records = int(grouped.loc[grouped['count'] == 1, 'count'].sum())

    if k_value == 1:
        risk_level = 'HIGH'
    elif k_value <= 3:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'LOW'

    return {
        'k_value':           k_value,
        'total_records':     int(len(df)),
        'total_eq_classes':  int(len(grouped)),
        'singleton_classes': singleton_classes,
        'singleton_records': singleton_records,
        'risk_level':        risk_level,
    }


def get_riskiest_classes(
    df: pd.DataFrame,
    qi_columns: List[str],
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Return the *top_n* smallest (most re-identifiable) equivalence classes.

    Results are sorted by class size ascending.
    """
    _, grouped = compute_equivalence_classes(df, qi_columns)
    if grouped.empty:
        return grouped
    return grouped.sort_values('count').head(top_n).reset_index(drop=True)


def validate_risk(
    df: pd.DataFrame,
    qi_columns: List[str],
) -> Dict[str, Any]:
    """
    Full risk-validation report for the dataset.

    Combines k-anonymity stats, riskiest classes, and an overall risk
    assessment into a single JSON-serialisable dict.

    Returns::

        {
          "k_anonymity": { k_value, total_records, total_eq_classes,
                           singleton_classes, singleton_records, risk_level },
          "riskiest_classes": [ {"count": N, "risk_percent": P, ...qi_values} ],
          "risk_summary": {
              "overall_risk":        "HIGH" | "MEDIUM" | "LOW",
              "recommendation":       "...",
              "percentage_at_risk":   float
          }
        }
    """
    k_stats = compute_k_anonymity(df, qi_columns)

    riskiest_df   = get_riskiest_classes(df, qi_columns, top_n=10)
    riskiest_list: List[Dict] = []
    if not riskiest_df.empty:
        for _, row in riskiest_df.iterrows():
            riskiest_list.append({
                str(k): (
                    int(v)   if isinstance(v, np.integer)  else
                    float(v) if isinstance(v, np.floating) else v
                )
                for k, v in row.items()
            })

    singleton_pct = (
        k_stats['singleton_records'] / k_stats['total_records'] * 100
        if k_stats['total_records'] > 0 else 0.0
    )

    risk_level = k_stats['risk_level']
    if risk_level == 'HIGH':
        recommendation = (
            'Significant re-identification risk detected. '
            'Apply generalisation or suppression to increase k-anonymity before release.'
        )
    elif risk_level == 'MEDIUM':
        recommendation = (
            'Moderate risk. Consider additional anonymisation techniques '
            'such as generalisation or adding k-anonymity constraints.'
        )
    else:
        recommendation = (
            'Risk is acceptable. Continue to monitor after applying anonymisation.'
        )

    return {
        'k_anonymity':    k_stats,
        'riskiest_classes': riskiest_list,
        'risk_summary': {
            'overall_risk':      risk_level,
            'recommendation':    recommendation,
            'percentage_at_risk': round(singleton_pct, 2),
        },
    }
