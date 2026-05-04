"""
Risk validation module for k-anonymity and privacy risk assessment.

Computes k-anonymity, uniqueness metrics, and identifies risky equivalence classes.
Also includes QI-combination search, l-diversity, and risk-level classification
ported from the original SDC Privacy Anonymization Tool (src/risk.py).
"""

import itertools
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Any


# ---------------------------------------------------------------------------
# Equivalence-class computation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# k-anonymity
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Risk-level classification (considers both k_min and unique_pct)
# ---------------------------------------------------------------------------

def get_risk_level(k_min: int, unique_pct: float) -> str:
    """
    Determine the risk level based on k-anonymity minimum and uniqueness
    percentage.  Ported from the original SDC tool (src/risk.py).

    Args:
        k_min:      Minimum equivalence-class size (k-anonymity).
        unique_pct: Percentage of equivalence classes that are singletons.

    Returns:
        One of "CRITICAL", "HIGH", "MEDIUM", "LOW".
    """
    if k_min == 1 and unique_pct >= 50:
        return "CRITICAL"
    elif k_min == 1 and unique_pct >= 20:
        return "HIGH"
    elif k_min <= 2 and unique_pct >= 10:
        return "MEDIUM"
    else:
        return "LOW"


# ---------------------------------------------------------------------------
# Riskiest equivalence classes
# ---------------------------------------------------------------------------

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


def get_risky_groups(
    df: pd.DataFrame,
    qi_cols: List[str],
    top_n: int = 10,
) -> Any:
    """
    Return the smallest equivalence classes for a QI combination.
    This shows which attribute combinations cause re-identification risk.

    Ported from the original SDC tool (src/risk.py).

    Args:
        df:      DataFrame to analyse.
        qi_cols: List of quasi-identifier column names.
        top_n:   Number of risky groups to return.

    Returns:
        DataFrame with the smallest groups, or None if no QI columns.
    """
    if not qi_cols:
        return None

    valid_cols = [c for c in qi_cols if c in df.columns]
    if not valid_cols:
        return None

    grouped = df.groupby(valid_cols, dropna=False).size().reset_index(name="group_size")
    risky = grouped.sort_values("group_size").head(top_n)
    return risky


# ---------------------------------------------------------------------------
# QI-combination search (ported from old src/risk.py)
# ---------------------------------------------------------------------------

def search_qi_combinations(
    df: pd.DataFrame,
    candidate_cols: List[str],
    max_comb_size: int = 3,
) -> List[Dict[str, Any]]:
    """
    Test all 1..max_comb_size combinations of *candidate_cols*, compute
    k-anonymity for each, and return the results sorted by risk (ascending
    k_min, then descending unique_pct).

    Ported from the original SDC tool (src/risk.py → search_qi_combinations).

    Args:
        df:             DataFrame to analyse.
        candidate_cols: List of candidate QI column names.
        max_comb_size:  Maximum number of columns per combination (1–4).

    Returns:
        List of dicts, each containing:
            qi_cols, comb_size, k_min, unique_pct, total_groups,
            avg_group_size, max_group_size, unique_groups, risk_level
    """
    results: List[Dict[str, Any]] = []

    # Only keep columns that actually exist in the dataframe
    valid_cols = [c for c in candidate_cols if c in df.columns]
    if not valid_cols:
        return results

    for r in range(1, min(max_comb_size, len(valid_cols)) + 1):
        for combo in itertools.combinations(valid_cols, r):
            combo_list = list(combo)
            _, class_sizes = compute_equivalence_classes(df, combo_list)

            if class_sizes.empty:
                continue

            sizes = class_sizes['class_size'].values
            k_min = int(sizes.min())
            max_group_size = int(sizes.max())
            avg_group_size = float(sizes.mean())
            total_groups = int(len(class_sizes))
            unique_groups = int((sizes == 1).sum())
            unique_pct = float((unique_groups / total_groups) * 100) if total_groups > 0 else 0.0

            risk_level = get_risk_level(k_min, unique_pct)

            results.append({
                "qi_cols":        ",".join(combo),
                "comb_size":      r,
                "k_min":          k_min,
                "unique_pct":     round(unique_pct, 2),
                "total_groups":   total_groups,
                "avg_group_size": round(avg_group_size, 2),
                "max_group_size": max_group_size,
                "unique_groups":  unique_groups,
                "risk_level":     risk_level,
            })

    # Sort: lowest k_min first, then highest unique_pct first
    results.sort(key=lambda x: (x["k_min"], -x["unique_pct"]))

    return results


# ---------------------------------------------------------------------------
# l-diversity (ported from old src/risk.py)
# ---------------------------------------------------------------------------

def compute_l_diversity(
    df: pd.DataFrame,
    qi_cols: List[str],
    sensitive_col: str,
) -> Any:
    """
    Compute l-diversity for each equivalence class formed by *qi_cols*
    with respect to a selected sensitive attribute.

    l-diversity measures how many distinct values the sensitive attribute
    takes within each equivalence class.

    Ported from the original SDC tool (src/risk.py → compute_l_diversity).

    Args:
        df:            DataFrame to analyse.
        qi_cols:       List of quasi-identifier column names.
        sensitive_col: Name of the sensitive attribute column.

    Returns:
        Dict with keys: sensitive_attribute, min_l_diversity, details (DataFrame).
        Returns None if inputs are invalid.
    """
    valid_cols = [c for c in qi_cols if c in df.columns]
    if not valid_cols or sensitive_col not in df.columns:
        return None

    grouped = (
        df.groupby(valid_cols, dropna=False)[sensitive_col]
        .nunique(dropna=True)
        .reset_index(name="l_diversity")
    )

    grouped["sensitive_attribute"] = sensitive_col

    min_l = int(grouped["l_diversity"].min())

    # Convert details to list of dicts for JSON serialisation
    details_records = grouped.sort_values(
        ["l_diversity"], ascending=True
    ).head(20).to_dict(orient="records")

    # Ensure numpy types are converted
    for row in details_records:
        for k, v in row.items():
            if isinstance(v, (np.integer,)):
                row[k] = int(v)
            elif isinstance(v, (np.floating,)):
                row[k] = float(v)

    return {
        "sensitive_attribute": sensitive_col,
        "min_l_diversity":     min_l,
        "details":             details_records,
    }


# ---------------------------------------------------------------------------
# Detailed evidence for a single QI combination
# ---------------------------------------------------------------------------

def get_detailed_evidence(
    df: pd.DataFrame,
    qi_cols: List[str],
) -> Dict[str, Any]:
    """
    Return detailed k-anonymity evidence for a single QI combination,
    including group-size distribution data.

    Args:
        df:      DataFrame to analyse.
        qi_cols: List of quasi-identifier column names.

    Returns:
        Dict with full risk evidence metrics.
    """
    valid_cols = [c for c in qi_cols if c in df.columns]
    if not valid_cols:
        return {"error": "No valid QI columns found"}

    _, class_sizes = compute_equivalence_classes(df, valid_cols)

    if class_sizes.empty:
        return {"error": "No equivalence classes could be computed"}

    sizes = class_sizes['class_size'].values
    k_min = int(sizes.min())
    unique_groups = int((sizes == 1).sum())
    total_groups = int(len(class_sizes))
    total_records = int(sizes.sum())
    unique_pct = float((unique_groups / total_groups) * 100) if total_groups > 0 else 0.0
    records_in_unique = int(class_sizes.loc[class_sizes['class_size'] == 1, 'class_size'].sum())
    risk_level = get_risk_level(k_min, unique_pct)

    # Group size distribution: {size: count_of_groups_with_that_size}
    dist = class_sizes['class_size'].value_counts().sort_index()
    group_size_distribution = {int(k): int(v) for k, v in dist.items()}

    # Top risky groups (smallest equivalence classes with their QI values)
    risky_groups_df = class_sizes.sort_values('class_size').head(10)
    risky_groups = []
    for _, row in risky_groups_df.iterrows():
        group_dict = {}
        for col in risky_groups_df.columns:
            val = row[col]
            if isinstance(val, (np.integer,)):
                group_dict[col] = int(val)
            elif isinstance(val, (np.floating,)):
                group_dict[col] = float(val)
            else:
                group_dict[col] = val
        risky_groups.append(group_dict)

    return {
        "qi_columns":              valid_cols,
        "k_min":                   k_min,
        "unique_pct":              round(unique_pct, 2),
        "risk_level":              risk_level,
        "total_groups":            total_groups,
        "unique_groups":           unique_groups,
        "records_in_unique_groups": records_in_unique,
        "avg_group_size":          round(float(sizes.mean()), 2),
        "max_group_size":          int(sizes.max()),
        "total_records":           total_records,
        "group_size_distribution": group_size_distribution,
        "risky_groups":            risky_groups,
    }


# ---------------------------------------------------------------------------
# Comprehensive risk validation (existing — kept for backward compatibility)
# ---------------------------------------------------------------------------

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
