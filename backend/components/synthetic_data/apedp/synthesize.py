"""
Synthetic Data Generation Module
Orchestrates the synthesis process using DP marginals + permutation.
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from .identify import get_columns_by_role, prepare_dataframe
from .dp import (
    dp_categorical_marginal,
    dp_numeric_marginal,
    sample_from_dp_categorical,
    sample_from_dp_numeric
)
from .permutation import apply_stratified_permutation


def generate_synthetic_data(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    epsilon: float,
    strata_keys: List[str],
    n_rows: Optional[int] = None,
    seed: Optional[int] = None,
    columns_to_synthesize: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Generate synthetic data from DP marginals with final permutation pass.
    
    Args:
        df: Clean input DataFrame (direct identifiers already dropped)
        metadata_df: Metadata DataFrame from identify_columns
        epsilon: Privacy parameter
        strata_keys: List of column names to use as strata
        n_rows: Number of rows to generate (default: same as input)
        seed: Random seed
        columns_to_synthesize: Optional list of columns to synthesize.
                              If None, synthesizes quasi-identifiers + sensitive.
    
    Returns:
        Synthetic DataFrame
    """
    if seed is not None:
        np.random.seed(seed)
    
    if n_rows is None:
        n_rows = len(df)
    
    if epsilon <= 0:
        raise ValueError("epsilon must be > 0")
    
    if columns_to_synthesize is None:
        quasi_cols = get_columns_by_role(metadata_df, 'Quasi-identifier')
        sensitive_cols = get_columns_by_role(metadata_df, 'Sensitive')
        columns_to_synthesize = quasi_cols + sensitive_cols
        columns_to_synthesize = [c for c in columns_to_synthesize if c in df.columns]
    
    categorical_cols = []
    numeric_cols = []
    for col in columns_to_synthesize:
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(col)
        else:
            categorical_cols.append(col)
    
    synthetic_df = pd.DataFrame(index=range(n_rows))
    dp_marginals = {}
    
    for col in columns_to_synthesize:
        if col not in df.columns:
            continue
        
        series = df[col]
        
        if col in categorical_cols:
            marginal = dp_categorical_marginal(series, epsilon, seed=seed)
            dp_marginals[col] = marginal
            samples = sample_from_dp_categorical(marginal, n_rows, seed=seed)
            synthetic_df[col] = samples
        else:
            marginal = dp_numeric_marginal(series, epsilon, n_bins=20, seed=seed)
            dp_marginals[col] = marginal
            samples = sample_from_dp_numeric(marginal, n_rows, seed=seed)
            synthetic_df[col] = samples
    
    strata_to_add = [k for k in strata_keys if k not in synthetic_df.columns and k in df.columns]
    
    if strata_to_add:
        try:
            if len(df) >= n_rows:
                strata_sample = df[strata_to_add].sample(n=n_rows, random_state=seed, replace=False)
            else:
                strata_sample = df[strata_to_add].sample(n=n_rows, random_state=seed, replace=True)
            for col in strata_to_add:
                synthetic_df[col] = strata_sample[col].values
        except Exception as e:
            print(f"Warning: Failed to add strata columns: {e}")
    
    if strata_keys and all(k in synthetic_df.columns for k in strata_keys):
        try:
            cols_to_permute = [c for c in columns_to_synthesize if c in synthetic_df.columns and c not in strata_keys]
            if cols_to_permute:
                categorical_cols_to_permute = [c for c in cols_to_permute if c in categorical_cols]
                synthetic_df = apply_stratified_permutation(
                    synthetic_df,
                    cols_to_permute,
                    strata_keys,
                    seed=seed,
                    categorical_columns=categorical_cols_to_permute
                )
        except Exception as e:
            print(f"Warning: Stratified permutation failed: {e}")
    
    for col in df.columns:
        if col not in synthetic_df.columns and col not in columns_to_synthesize:
            if len(df) >= n_rows:
                synthetic_df[col] = df[col].sample(n=n_rows, random_state=seed, replace=False).values
            else:
                synthetic_df[col] = df[col].sample(n=n_rows, random_state=seed, replace=True).values
    
    return synthetic_df


def self_check(
    original_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    n_rows: int,
    epsilon: float
) -> Dict[str, bool]:
    """
    Self-check function to validate synthesis output.
    
    Returns:
        Dictionary of check results
    """
    results = {}
    
    direct_ids = get_columns_by_role(metadata_df, 'Direct Identifier')
    results['no_direct_identifiers'] = all(col not in synthetic_df.columns for col in direct_ids)
    results['row_count_match'] = len(synthetic_df) == n_rows
    
    total_cells = len(synthetic_df) * len(synthetic_df.columns)
    nan_count = synthetic_df.isna().sum().sum()
    results['no_nan_explosion'] = nan_count < total_cells * 0.5
    
    results['epsilon_valid'] = epsilon > 0
    
    return results


from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from .identify import get_columns_by_role
from .dp import (
    dp_categorical_marginal, dp_numeric_marginal,
    sample_from_dp_categorical, sample_from_dp_numeric,
)
from .permutation import apply_stratified_permutation


def generate_synthetic_data(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    epsilon: float,
    strata_keys: List[str],
    n_rows: Optional[int] = None,
    seed: Optional[int] = None,
    columns_to_synthesize: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Generate synthetic data using DP-marginals + stratified permutation.

    Args:
        df: Clean DataFrame (direct identifiers already dropped).
        metadata_df: Column classification DataFrame from identify_columns().
        epsilon: Privacy budget (must be > 0).
        strata_keys: Columns used for stratified permutation.
        n_rows: Output row count (defaults to len(df)).
        seed: Random seed.
        columns_to_synthesize: Override list; defaults to quasi + sensitive cols.

    Returns:
        Synthetic DataFrame.
    """
    if seed is not None:
        np.random.seed(seed)

    if n_rows is None:
        n_rows = len(df)

    if epsilon <= 0:
        raise ValueError("epsilon must be > 0")

    # Determine columns to synthesize
    if columns_to_synthesize is None:
        quasi_cols = get_columns_by_role(metadata_df, 'Quasi-identifier')
        sensitive_cols = get_columns_by_role(metadata_df, 'Sensitive')
        columns_to_synthesize = [c for c in (quasi_cols + sensitive_cols) if c in df.columns]

    categorical_cols = [c for c in columns_to_synthesize if not pd.api.types.is_numeric_dtype(df[c])]
    numeric_cols_synth = [c for c in columns_to_synthesize if pd.api.types.is_numeric_dtype(df[c])]

    synthetic_df = pd.DataFrame(index=range(n_rows))

    # Generate each column from DP marginals
    for col in columns_to_synthesize:
        if col not in df.columns:
            continue
        series = df[col]
        if col in categorical_cols:
            marginal = dp_categorical_marginal(series, epsilon, seed=seed)
            synthetic_df[col] = sample_from_dp_categorical(marginal, n_rows, seed=seed)
        else:
            marginal = dp_numeric_marginal(series, epsilon, n_bins=20, seed=seed)
            synthetic_df[col] = sample_from_dp_numeric(marginal, n_rows, seed=seed)

    # Add strata columns that weren't synthesized (needed for permutation)
    strata_to_add = [k for k in strata_keys if k not in synthetic_df.columns and k in df.columns]
    if strata_to_add:
        try:
            replace = len(df) < n_rows
            strata_sample = df[strata_to_add].sample(n=n_rows, random_state=seed, replace=replace)
            for col in strata_to_add:
                synthetic_df[col] = strata_sample[col].values
        except Exception as e:
            print(f"Warning: Failed to add strata columns: {e}")

    # Apply stratified permutation
    if strata_keys and all(k in synthetic_df.columns for k in strata_keys):
        try:
            cols_to_permute = [c for c in columns_to_synthesize if c in synthetic_df.columns and c not in strata_keys]
            if cols_to_permute:
                cat_to_permute = [c for c in cols_to_permute if c in categorical_cols]
                synthetic_df = apply_stratified_permutation(
                    synthetic_df, cols_to_permute, strata_keys,
                    seed=seed, categorical_columns=cat_to_permute,
                )
        except Exception as e:
            print(f"Warning: Stratified permutation failed: {e}")

    # Copy remaining unsynthesized columns by sampling from original
    for col in df.columns:
        if col not in synthetic_df.columns:
            replace = len(df) < n_rows
            synthetic_df[col] = df[col].sample(n=n_rows, random_state=seed, replace=replace).values

    return synthetic_df


def self_check(
    original_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    n_rows: int,
    epsilon: float,
) -> Dict[str, bool]:
    direct_ids = get_columns_by_role(metadata_df, 'Direct Identifier')
    total_cells = max(1, len(synthetic_df) * len(synthetic_df.columns))
    nan_count = synthetic_df.isna().sum().sum()
    return {
        'no_direct_identifiers': all(col not in synthetic_df.columns for col in direct_ids),
        'row_count_match': len(synthetic_df) == n_rows,
        'no_nan_explosion': nan_count < total_cells * 0.5,
        'epsilon_valid': epsilon > 0,
    }
