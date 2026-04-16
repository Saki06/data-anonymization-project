"""
Reporting Module
Generates utility and privacy metrics reports.
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from scipy import stats


def total_variation_distance(real: pd.Series, synthetic: pd.Series) -> float:
    """Compute Total Variation Distance between two categorical distributions."""
    real_counts = real.value_counts(normalize=True)
    synthetic_counts = synthetic.value_counts(normalize=True)
    all_values = set(real_counts.index) | set(synthetic_counts.index)
    tvd = 0.0
    for value in all_values:
        real_prob = real_counts.get(value, 0.0)
        synthetic_prob = synthetic_counts.get(value, 0.0)
        tvd += abs(real_prob - synthetic_prob)
    return tvd / 2.0


def kolmogorov_smirnov_statistic(real: pd.Series, synthetic: pd.Series) -> float:
    """Compute Kolmogorov-Smirnov statistic between two numeric distributions."""
    real_clean = real.dropna()
    synthetic_clean = synthetic.dropna()
    if len(real_clean) == 0 or len(synthetic_clean) == 0:
        return 1.0
    ks_stat, _ = stats.ks_2samp(real_clean, synthetic_clean)
    return ks_stat


def missingness_comparison(real: pd.Series, synthetic: pd.Series) -> Dict:
    """Compare missingness between real and synthetic data."""
    real_missing = real.isna().sum()
    synthetic_missing = synthetic.isna().sum()
    real_pct = (real_missing / len(real)) * 100 if len(real) > 0 else 0
    synthetic_pct = (synthetic_missing / len(synthetic)) * 100 if len(synthetic) > 0 else 0
    return {
        'real_missing_count': int(real_missing),
        'real_missing_pct': float(real_pct),
        'synthetic_missing_count': int(synthetic_missing),
        'synthetic_missing_pct': float(synthetic_pct),
        'difference_pct': float(abs(real_pct - synthetic_pct))
    }


def nearest_neighbor_distances(
    real_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    numeric_columns: List[str],
    k: int = 1
) -> Dict:
    """Compute nearest-neighbor distances as privacy proxy."""
    if not numeric_columns:
        return {'mean_real_to_real': None, 'mean_real_to_synthetic': None,
                'min_real_to_real': None, 'min_real_to_synthetic': None, 'privacy_ratio': None}
    
    numeric_cols = [c for c in numeric_columns if c in real_df.columns and c in synthetic_df.columns]
    if not numeric_cols:
        return {'mean_real_to_real': None, 'mean_real_to_synthetic': None,
                'min_real_to_real': None, 'min_real_to_synthetic': None, 'privacy_ratio': None}
    
    real_numeric = real_df[numeric_cols].dropna()
    synthetic_numeric = synthetic_df[numeric_cols].dropna()
    
    if len(real_numeric) == 0 or len(synthetic_numeric) == 0:
        return {'mean_real_to_real': None, 'mean_real_to_synthetic': None,
                'min_real_to_real': None, 'min_real_to_synthetic': None, 'privacy_ratio': None}
    
    from sklearn.preprocessing import StandardScaler
    from sklearn.neighbors import NearestNeighbors
    
    scaler = StandardScaler()
    real_scaled = scaler.fit_transform(real_numeric)
    synthetic_scaled = scaler.transform(synthetic_numeric)
    
    nn_real = NearestNeighbors(n_neighbors=k + 1, metric='euclidean')
    nn_real.fit(real_scaled)
    distances_real_to_real, _ = nn_real.kneighbors(real_scaled)
    distances_real_to_real = distances_real_to_real[:, 1:]
    
    distances_real_to_synthetic, _ = nn_real.kneighbors(synthetic_scaled)
    distances_real_to_synthetic = distances_real_to_synthetic[:, :k]
    
    mean_rr = float(np.mean(distances_real_to_real))
    mean_rs = float(np.mean(distances_real_to_synthetic))
    min_rr = float(np.min(distances_real_to_real))
    min_rs = float(np.min(distances_real_to_synthetic))
    privacy_ratio = mean_rs / mean_rr if mean_rr > 0 else None
    
    return {
        'mean_real_to_real': mean_rr,
        'mean_real_to_synthetic': mean_rs,
        'min_real_to_real': min_rr,
        'min_real_to_synthetic': min_rs,
        'privacy_ratio': privacy_ratio
    }


def generate_report(
    original_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    epsilon: float,
    seed: Optional[int],
    strata_keys: List[str],
    dropped_columns: List[str],
    mapped_columns: Optional[List[str]] = None,
    codebook_used: bool = False
) -> Dict:
    """Generate comprehensive report with utility and privacy metrics."""
    from .identify import get_columns_by_role
    
    report = {
        'parameters': {
            'epsilon': float(epsilon),
            'seed': seed,
            'strata_keys': strata_keys,
            'n_rows_original': int(len(original_df)),
            'n_rows_synthetic': int(len(synthetic_df))
        },
        'columns_dropped': dropped_columns,
        'codebook': {
            'used': codebook_used,
            'mapped_columns': mapped_columns or []
        },
        'utility_metrics': {},
        'privacy_proxy': {},
        'notes': (
            'Privacy guarantees are provided by the Laplace mechanism with epsilon-DP. '
            'Utility metrics measure distributional similarity between real and synthetic data.'
        )
    }
    
    quasi_cols = get_columns_by_role(metadata_df, 'Quasi-identifier')
    sensitive_cols = get_columns_by_role(metadata_df, 'Sensitive')
    numeric_cols = [c for c in original_df.columns if pd.api.types.is_numeric_dtype(original_df[c])]
    
    utility_metrics = {}
    for col in original_df.columns:
        if col not in synthetic_df.columns:
            continue
        real_series = original_df[col]
        synthetic_series = synthetic_df[col]
        col_metrics = {}
        if not pd.api.types.is_numeric_dtype(real_series):
            col_metrics['total_variation_distance'] = float(total_variation_distance(real_series, synthetic_series))
        else:
            col_metrics['kolmogorov_smirnov'] = float(kolmogorov_smirnov_statistic(real_series, synthetic_series))
        col_metrics['missingness'] = missingness_comparison(real_series, synthetic_series)
        utility_metrics[col] = col_metrics
    
    report['utility_metrics'] = utility_metrics
    
    try:
        nn_distances = nearest_neighbor_distances(original_df, synthetic_df, numeric_cols, k=1)
        report['privacy_proxy'] = nn_distances
    except Exception as e:
        report['privacy_proxy'] = {'note': f'Nearest-neighbor analysis skipped: {e}'}
    
    return report


from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from .identify import get_columns_by_role


def total_variation_distance(real: pd.Series, synthetic: pd.Series) -> float:
    real_counts = real.value_counts(normalize=True)
    synthetic_counts = synthetic.value_counts(normalize=True)
    all_values = set(real_counts.index) | set(synthetic_counts.index)
    tvd = sum(abs(real_counts.get(v, 0.0) - synthetic_counts.get(v, 0.0)) for v in all_values)
    return tvd / 2.0


def kolmogorov_smirnov_statistic(real: pd.Series, synthetic: pd.Series) -> float:
    from scipy import stats
    real_clean = real.dropna()
    synthetic_clean = synthetic.dropna()
    if len(real_clean) == 0 or len(synthetic_clean) == 0:
        return 1.0
    ks_stat, _ = stats.ks_2samp(real_clean, synthetic_clean)
    return float(ks_stat)


def missingness_comparison(real: pd.Series, synthetic: pd.Series) -> Dict:
    real_missing = real.isna().sum()
    synthetic_missing = synthetic.isna().sum()
    real_pct = (real_missing / max(len(real), 1)) * 100
    synthetic_pct = (synthetic_missing / max(len(synthetic), 1)) * 100
    return {
        'real_missing_count': int(real_missing),
        'real_missing_pct': float(real_pct),
        'synthetic_missing_count': int(synthetic_missing),
        'synthetic_missing_pct': float(synthetic_pct),
        'difference_pct': float(abs(real_pct - synthetic_pct)),
    }


def nearest_neighbor_distances(real_df: pd.DataFrame, synthetic_df: pd.DataFrame, numeric_columns: List[str], k: int = 1) -> Dict:
    if not numeric_columns:
        return {'privacy_ratio': None, 'note': 'No numeric columns available'}
    numeric_cols = [c for c in numeric_columns if c in real_df.columns and c in synthetic_df.columns]
    if not numeric_cols:
        return {'privacy_ratio': None, 'note': 'Numeric columns not in both DataFrames'}
    try:
        from sklearn.preprocessing import StandardScaler
        from sklearn.neighbors import NearestNeighbors
        real_numeric = real_df[numeric_cols].dropna()
        synthetic_numeric = synthetic_df[numeric_cols].dropna()
        if len(real_numeric) == 0 or len(synthetic_numeric) == 0:
            return {'privacy_ratio': None}
        scaler = StandardScaler()
        real_scaled = scaler.fit_transform(real_numeric)
        synthetic_scaled = scaler.transform(synthetic_numeric)
        nn_real = NearestNeighbors(n_neighbors=k + 1, metric='euclidean')
        nn_real.fit(real_scaled)
        d_real_to_real, _ = nn_real.kneighbors(real_scaled)
        d_real_to_real = d_real_to_real[:, 1:]
        d_real_to_synth, _ = nn_real.kneighbors(synthetic_scaled)
        d_real_to_synth = d_real_to_synth[:, :k]
        mean_r2r = float(np.mean(d_real_to_real))
        mean_r2s = float(np.mean(d_real_to_synth))
        min_r2r = float(np.min(d_real_to_real))
        min_r2s = float(np.min(d_real_to_synth))
        privacy_ratio = mean_r2s / mean_r2r if mean_r2r > 0 else None
        return {
            'mean_real_to_real': mean_r2r,
            'mean_real_to_synthetic': mean_r2s,
            'min_real_to_real': min_r2r,
            'min_real_to_synthetic': min_r2s,
            'privacy_ratio': privacy_ratio,
        }
    except Exception as e:
        return {'privacy_ratio': None, 'note': f'NN analysis skipped: {e}'}


def generate_report(
    original_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    epsilon: float,
    seed: Optional[int],
    strata_keys: List[str],
    dropped_columns: List[str],
    mapped_columns: Optional[List[str]] = None,
    codebook_used: bool = False,
) -> Dict:
    report: Dict = {
        'parameters': {
            'epsilon': float(epsilon),
            'seed': seed,
            'strata_keys': strata_keys,
            'n_rows_original': int(len(original_df)),
            'n_rows_synthetic': int(len(synthetic_df)),
        },
        'columns_dropped': dropped_columns,
        'codebook': {'used': codebook_used, 'mapped_columns': mapped_columns or []},
        'utility_metrics': {},
        'privacy_proxy': {},
        'notes': (
            'APEDP: DP-marginals (Laplace mechanism, epsilon-DP) + stratified permutation. '
            'Utility metrics measure distributional similarity between real and synthetic data.'
        ),
    }

    numeric_cols = [c for c in original_df.columns if pd.api.types.is_numeric_dtype(original_df[c])]
    utility_metrics: Dict = {}

    for col in original_df.columns:
        if col not in synthetic_df.columns:
            continue
        real_series = original_df[col]
        synthetic_series = synthetic_df[col]
        col_metrics: Dict = {}
        try:
            if not pd.api.types.is_numeric_dtype(real_series):
                col_metrics['total_variation_distance'] = float(total_variation_distance(real_series, synthetic_series))
            else:
                col_metrics['kolmogorov_smirnov'] = float(kolmogorov_smirnov_statistic(real_series, synthetic_series))
        except Exception:
            pass
        col_metrics['missingness'] = missingness_comparison(real_series, synthetic_series)
        utility_metrics[col] = col_metrics

    report['utility_metrics'] = utility_metrics

    try:
        report['privacy_proxy'] = nearest_neighbor_distances(original_df, synthetic_df, numeric_cols)
    except Exception as e:
        report['privacy_proxy'] = {'note': f'Skipped: {e}'}

    return report
