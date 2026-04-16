"""
Differential Privacy Module
Implements Laplace mechanism for categorical and numeric columns.
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np


def laplace_noise(scale: float, size: int, seed: Optional[int] = None) -> np.ndarray:
    """
    Generate Laplace noise.
    
    Args:
        scale: Scale parameter (1/epsilon)
        size: Number of samples
        seed: Random seed
        
    Returns:
        Array of Laplace noise
    """
    if seed is not None:
        np.random.seed(seed)
    return np.random.laplace(0, scale, size)


def dp_categorical_marginal(
    series: pd.Series,
    epsilon: float,
    seed: Optional[int] = None
) -> Dict:
    """
    Compute differentially private marginal distribution for categorical column.
    
    Args:
        series: Input Series
        epsilon: Privacy parameter (must be > 0)
        seed: Random seed
        
    Returns:
        Dictionary with:
        - 'distribution': Dict mapping values to probabilities
        - 'noisy_counts': Dict mapping values to noisy counts
    """
    if epsilon <= 0:
        raise ValueError("epsilon must be > 0")
    
    if seed is not None:
        np.random.seed(seed)
    
    value_counts = series.value_counts()
    
    scale = 1.0 / epsilon
    noisy_counts = {}
    for value, count in value_counts.items():
        noise = np.random.laplace(0, scale)
        noisy_count = count + noise
        noisy_counts[value] = max(0, noisy_count)
    
    total_noisy = sum(noisy_counts.values())
    if total_noisy <= 0:
        n_unique = len(value_counts)
        for value in value_counts.index:
            noisy_counts[value] = 1.0 / n_unique
        total_noisy = 1.0
    
    distribution = {k: v / total_noisy for k, v in noisy_counts.items()}
    
    return {
        'distribution': distribution,
        'noisy_counts': noisy_counts
    }


def dp_numeric_marginal(
    series: pd.Series,
    epsilon: float,
    n_bins: int = 20,
    seed: Optional[int] = None
) -> Dict:
    """
    Compute differentially private marginal distribution for numeric column.
    
    Args:
        series: Input Series (numeric)
        epsilon: Privacy parameter (must be > 0)
        n_bins: Number of bins for histogram
        seed: Random seed
        
    Returns:
        Dictionary with bins, bin_centers, probabilities, noisy_counts, min/max.
    """
    if epsilon <= 0:
        raise ValueError("epsilon must be > 0")
    
    if seed is not None:
        np.random.seed(seed)
    
    clean_series = series.dropna()
    
    if len(clean_series) == 0:
        raise ValueError("Series contains only NaN values")
    
    min_val = float(clean_series.min())
    max_val = float(clean_series.max())
    
    if min_val == max_val:
        return {
            'bins': np.array([min_val - 0.5, min_val + 0.5]),
            'bin_centers': np.array([min_val]),
            'probabilities': np.array([1.0]),
            'noisy_counts': np.array([1.0]),
            'min_value': min_val,
            'max_value': max_val
        }
    
    bins = np.linspace(min_val, max_val, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    
    counts, _ = np.histogram(clean_series, bins=bins)
    
    scale = 1.0 / epsilon
    noisy_counts = counts.astype(float) + np.random.laplace(0, scale, size=len(counts))
    noisy_counts = np.maximum(0, noisy_counts)
    
    total_noisy = noisy_counts.sum()
    if total_noisy <= 0:
        noisy_counts = np.ones(n_bins) / n_bins
        total_noisy = 1.0
    
    probabilities = noisy_counts / total_noisy
    
    return {
        'bins': bins,
        'bin_centers': bin_centers,
        'probabilities': probabilities,
        'noisy_counts': noisy_counts,
        'min_value': min_val,
        'max_value': max_val
    }


def sample_from_dp_categorical(distribution: Dict, n: int, seed: Optional[int] = None) -> np.ndarray:
    """
    Sample n values from DP categorical distribution.
    
    Args:
        distribution: Distribution dictionary from dp_categorical_marginal
        n: Number of samples
        seed: Random seed
        
    Returns:
        Array of sampled values
    """
    if seed is not None:
        np.random.seed(seed)
    
    values = list(distribution['distribution'].keys())
    probabilities = list(distribution['distribution'].values())
    
    return np.random.choice(values, size=n, p=probabilities)


def sample_from_dp_numeric(marginal: Dict, n: int, seed: Optional[int] = None) -> np.ndarray:
    """
    Sample n values from DP numeric distribution.
    
    Args:
        marginal: Marginal dictionary from dp_numeric_marginal
        n: Number of samples
        seed: Random seed
        
    Returns:
        Array of sampled values
    """
    if seed is not None:
        np.random.seed(seed)
    
    bins = marginal['bins']
    probabilities = marginal['probabilities']
    
    bin_indices = np.random.choice(len(probabilities), size=n, p=probabilities)
    
    samples = []
    for idx in bin_indices:
        bin_left = bins[idx]
        bin_right = bins[idx + 1]
        sample = np.random.uniform(bin_left, bin_right)
        samples.append(sample)
    
    return np.array(samples)


from typing import Dict, Optional
import pandas as pd
import numpy as np


def laplace_noise(scale: float, size: int, seed: Optional[int] = None) -> np.ndarray:
    if seed is not None:
        np.random.seed(seed)
    return np.random.laplace(0, scale, size)


def dp_categorical_marginal(series: pd.Series, epsilon: float, seed: Optional[int] = None) -> Dict:
    if epsilon <= 0:
        raise ValueError("epsilon must be > 0")
    if seed is not None:
        np.random.seed(seed)
    value_counts = series.value_counts()
    scale = 1.0 / epsilon
    noisy_counts = {}
    for value, count in value_counts.items():
        noise = np.random.laplace(0, scale)
        noisy_counts[value] = max(0, count + noise)
    total_noisy = sum(noisy_counts.values())
    if total_noisy <= 0:
        n_unique = max(1, len(value_counts))
        for value in value_counts.index:
            noisy_counts[value] = 1.0 / n_unique
        total_noisy = 1.0
    distribution = {k: v / total_noisy for k, v in noisy_counts.items()}
    return {'distribution': distribution, 'noisy_counts': noisy_counts}


def dp_numeric_marginal(series: pd.Series, epsilon: float, n_bins: int = 20, seed: Optional[int] = None) -> Dict:
    if epsilon <= 0:
        raise ValueError("epsilon must be > 0")
    if seed is not None:
        np.random.seed(seed)
    clean_series = series.dropna()
    if len(clean_series) == 0:
        raise ValueError("Series contains only NaN values")
    min_val = float(clean_series.min())
    max_val = float(clean_series.max())
    if min_val == max_val:
        return {
            'bins': np.array([min_val - 0.5, min_val + 0.5]),
            'bin_centers': np.array([min_val]),
            'probabilities': np.array([1.0]),
            'noisy_counts': np.array([1.0]),
            'min_value': min_val,
            'max_value': max_val,
        }
    bins = np.linspace(min_val, max_val, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    counts, _ = np.histogram(clean_series, bins=bins)
    scale = 1.0 / epsilon
    noisy_counts = np.maximum(0, counts.astype(float) + np.random.laplace(0, scale, size=len(counts)))
    total_noisy = noisy_counts.sum()
    if total_noisy <= 0:
        noisy_counts = np.ones(n_bins) / n_bins
        total_noisy = 1.0
    probabilities = noisy_counts / total_noisy
    return {
        'bins': bins,
        'bin_centers': bin_centers,
        'probabilities': probabilities,
        'noisy_counts': noisy_counts,
        'min_value': min_val,
        'max_value': max_val,
    }


def sample_from_dp_categorical(distribution: Dict, n: int, seed: Optional[int] = None) -> np.ndarray:
    if seed is not None:
        np.random.seed(seed)
    values = list(distribution['distribution'].keys())
    probabilities = list(distribution['distribution'].values())
    return np.random.choice(values, size=n, p=probabilities)


def sample_from_dp_numeric(marginal: Dict, n: int, seed: Optional[int] = None) -> np.ndarray:
    if seed is not None:
        np.random.seed(seed)
    bins = marginal['bins']
    probabilities = marginal['probabilities']
    bin_indices = np.random.choice(len(probabilities), size=n, p=probabilities)
    samples = []
    for idx in bin_indices:
        sample = np.random.uniform(bins[idx], bins[idx + 1])
        samples.append(sample)
    return np.array(samples)
