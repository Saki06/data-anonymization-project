"""
Permutation Module (Permutation Paradigm)
Implements stratified permutation within strata groups.
"""

from typing import List, Optional
import pandas as pd
import numpy as np


def stratified_permute_categorical(
    df: pd.DataFrame,
    column: str,
    strata_keys: List[str],
    seed: Optional[int] = None
) -> pd.Series:
    """
    Permute categorical column values within each stratum.
    """
    if seed is not None:
        np.random.seed(seed)
    
    result = df[column].copy()
    
    for stratum, group_indices in df.groupby(strata_keys).groups.items():
        indices = group_indices.tolist()
        if len(indices) > 1:
            values = df.loc[indices, column].values
            np.random.shuffle(values)
            result.loc[indices] = values
    
    return result


def stratified_permute_numeric(
    df: pd.DataFrame,
    column: str,
    strata_keys: List[str],
    seed: Optional[int] = None
) -> pd.Series:
    """
    Permute numeric column using rank-based permutation within each stratum.
    """
    if seed is not None:
        np.random.seed(seed)
    
    result = df[column].copy()
    
    for stratum, group_indices in df.groupby(strata_keys).groups.items():
        indices = group_indices.tolist()
        if len(indices) > 1:
            values = df.loc[indices, column].values
            sorted_values = np.sort(values)
            ranks = np.arange(len(values))
            np.random.shuffle(ranks)
            result.loc[indices] = sorted_values[ranks]
    
    return result


def apply_stratified_permutation(
    df: pd.DataFrame,
    columns: List[str],
    strata_keys: List[str],
    seed: Optional[int] = None,
    categorical_columns: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Apply stratified permutation to specified columns.
    
    Args:
        df: Input DataFrame
        columns: List of column names to permute
        strata_keys: List of column names to use as strata
        categorical_columns: Optional list of categorical column names.
                           If None, inferred from dtypes.
        seed: Random seed for reproducibility
        
    Returns:
        DataFrame with permuted columns
    """
    if seed is not None:
        np.random.seed(seed)
    
    result = df.copy()
    
    if categorical_columns is None:
        categorical_columns = [
            col for col in df.columns
            if not pd.api.types.is_numeric_dtype(df[col])
        ]
    
    missing_strata = [k for k in strata_keys if k not in df.columns]
    if missing_strata:
        raise ValueError(f"Strata keys not found in DataFrame: {missing_strata}")
    
    for col in columns:
        if col not in df.columns:
            continue
        if col in categorical_columns:
            result[col] = stratified_permute_categorical(df, col, strata_keys, seed)
        else:
            result[col] = stratified_permute_numeric(df, col, strata_keys, seed)
    
    return result


from typing import List, Optional
import pandas as pd
import numpy as np


def stratified_permute_categorical(df: pd.DataFrame, column: str, strata_keys: List[str], seed: Optional[int] = None) -> pd.Series:
    if seed is not None:
        np.random.seed(seed)
    result = df[column].copy()
    for _, group_indices in df.groupby(strata_keys).groups.items():
        indices = group_indices.tolist()
        if len(indices) > 1:
            values = df.loc[indices, column].values.copy()
            np.random.shuffle(values)
            result.loc[indices] = values
    return result


def stratified_permute_numeric(df: pd.DataFrame, column: str, strata_keys: List[str], seed: Optional[int] = None) -> pd.Series:
    if seed is not None:
        np.random.seed(seed)
    result = df[column].copy()
    for _, group_indices in df.groupby(strata_keys).groups.items():
        indices = group_indices.tolist()
        if len(indices) > 1:
            values = df.loc[indices, column].values
            sorted_values = np.sort(values)
            ranks = np.arange(len(values))
            np.random.shuffle(ranks)
            result.loc[indices] = sorted_values[ranks]
    return result


def apply_stratified_permutation(
    df: pd.DataFrame,
    columns: List[str],
    strata_keys: List[str],
    seed: Optional[int] = None,
    categorical_columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    if seed is not None:
        np.random.seed(seed)
    result = df.copy()
    if categorical_columns is None:
        categorical_columns = [col for col in df.columns if not pd.api.types.is_numeric_dtype(df[col])]
    missing_strata = [k for k in strata_keys if k not in df.columns]
    if missing_strata:
        raise ValueError(f"Strata keys not found in DataFrame: {missing_strata}")
    for col in columns:
        if col not in df.columns:
            continue
        if col in categorical_columns:
            result[col] = stratified_permute_categorical(df, col, strata_keys, seed)
        else:
            result[col] = stratified_permute_numeric(df, col, strata_keys, seed)
    return result
