"""
Reporting Module
Generates utility and privacy metrics reports for APEDP synthetic data.

Utility metrics included:
  - Per-column: Total Variation Distance (categorical), Kolmogorov-Smirnov (numeric), Missingness
  - Global:     Propensity Score Utility (pMSE / Woo et al. statistic)
Privacy metrics:
  - Nearest-Neighbour Distance Ratio (NNDR)
  - CM3 (Confidentiality Metric based on Canonical Correlation Analysis)
    Reference: Domingo-Ferrer & Torra (2001) – "Disclosure Control Methods and
    Information Loss for Microdata". CM3 = min_j CM2(X_{-j}, Y_{-j}) where
    CM2 is the product of (1 − ρ_i²) over all canonical correlations.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-column utility helpers
# ---------------------------------------------------------------------------

def total_variation_distance(real: pd.Series, synthetic: pd.Series) -> float:
    """Compute Total Variation Distance between two categorical distributions."""
    real_counts = real.value_counts(normalize=True)
    synthetic_counts = synthetic.value_counts(normalize=True)
    all_values = set(real_counts.index) | set(synthetic_counts.index)
    tvd = sum(abs(real_counts.get(v, 0.0) - synthetic_counts.get(v, 0.0)) for v in all_values)
    return tvd / 2.0


def kolmogorov_smirnov_statistic(real: pd.Series, synthetic: pd.Series) -> float:
    """Compute Kolmogorov-Smirnov statistic between two numeric distributions."""
    real_clean = real.dropna()
    synthetic_clean = synthetic.dropna()
    if len(real_clean) == 0 or len(synthetic_clean) == 0:
        return 1.0
    ks_stat, _ = stats.ks_2samp(real_clean, synthetic_clean)
    return float(ks_stat)


def missingness_comparison(real: pd.Series, synthetic: pd.Series) -> Dict:
    """Compare missingness rates between real and synthetic columns."""
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


# ---------------------------------------------------------------------------
# Global utility: Propensity Score Utility (Woo et al. / pMSE)
# ---------------------------------------------------------------------------

def propensity_score_utility(
    real_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    max_iter: int = 300,
) -> Dict:
    """
    Compute the propensity score utility statistic U (Woo et al., 2009).

    Methodology
    -----------
    1. Stack the n original records and n synthetic records → 2n records.
    2. Add indicator I: original = 0, synthetic = 1.
    3. Fit a Logistic Regression classifier to predict I from the other attributes.
       Logistic Regression is deliberately chosen as a simple, low-order model to
       avoid overfitting (as recommended by Woo et al. and Snoke et al.).
    4. For each record i, obtain the predicted probability p̂_i.
    5. Compute U = (1 / 2n) * Σ (p̂_i − 0.5)²

    Interpretation
    --------------
    - U ≈ 0  → classifier cannot distinguish real from synthetic (good utility).
    - U → 0.25 → classifier perfectly separates the two sets (poor utility).
    - The theoretical null value (when real ≡ synthetic) is 0.

    Parameters
    ----------
    real_df : pd.DataFrame
        Original (real) data.
    synthetic_df : pd.DataFrame
        Synthetic data.
    max_iter : int
        Maximum iterations for Logistic Regression solver.

    Returns
    -------
    dict with keys:
        - ``propensity_score_U``  : float, the utility statistic (lower is better)
        - ``n_original``          : int
        - ``n_synthetic``         : int
        - ``classifier``          : str, name of model used
        - ``note``                : str, interpretation hint or error message
    """
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import LabelEncoder, StandardScaler

        # ── 1. Align columns (intersection) ─────────────────────────────────
        common_cols = [c for c in real_df.columns if c in synthetic_df.columns]
        if not common_cols:
            return {
                'propensity_score_U': None,
                'note': 'No common columns between real and synthetic data.',
            }

        real_sub = real_df[common_cols].copy()
        synth_sub = synthetic_df[common_cols].copy()

        # ── 2. Stack and label ───────────────────────────────────────────────
        real_sub['_indicator'] = 0
        synth_sub['_indicator'] = 1
        stacked = pd.concat([real_sub, synth_sub], ignore_index=True)

        y = stacked['_indicator'].values
        X = stacked.drop(columns=['_indicator'])

        # ── 3. Encode categoricals, impute, scale ───────────────────────────
        X_encoded = X.copy()
        for col in X_encoded.select_dtypes(include=['object', 'category']).columns:
            le = LabelEncoder()
            X_encoded[col] = le.fit_transform(X_encoded[col].astype(str))

        # Simple median imputation for any remaining NaNs
        for col in X_encoded.columns:
            if X_encoded[col].isna().any():
                X_encoded[col] = X_encoded[col].fillna(X_encoded[col].median())

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_encoded)

        # ── 4. Fit simple Logistic Regression (avoids overfitting) ──────────
        clf = LogisticRegression(
            C=1.0,           # standard regularisation strength
            max_iter=max_iter,
            solver='lbfgs',
            random_state=42,
        )
        clf.fit(X_scaled, y)

        # ── 5. Predict propensities and compute U ────────────────────────────
        p_hat = clf.predict_proba(X_scaled)[:, 1]   # P(synthetic)
        two_n = len(p_hat)
        U = float(np.sum((p_hat - 0.5) ** 2) / two_n)

        return {
            'propensity_score_U': round(U, 6),
            'n_original': int(len(real_df)),
            'n_synthetic': int(len(synthetic_df)),
            'classifier': 'LogisticRegression (C=1, lbfgs)',
            'note': (
                'U ≈ 0 indicates high utility (classifier cannot distinguish real '
                'from synthetic). Theoretical maximum is 0.25 (perfect separation).'
            ),
        }

    except Exception as e:
        return {
            'propensity_score_U': None,
            'note': f'Propensity score utility computation skipped: {e}',
        }


# ---------------------------------------------------------------------------
# Enhanced propensity score metric  (compute_propensity_score_metric)
# ---------------------------------------------------------------------------

def compute_propensity_score_metric(
    real_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    test_size: float = 0.2,
    max_iter: int = 500,
    return_probabilities: bool = False,
) -> Dict:
    """
    Full propensity-score utility metric (Woo et al., 2009 / Snoke et al., 2018).

    Steps
    -----
    1. Stack real (label=0) and synthetic (label=1) into one combined DataFrame.
    2. Encode categoricals (LabelEncoder), impute NaNs (median), standardise.
    3. Optional stratified train/test split to obtain out-of-sample accuracy.
    4. Fit a Logistic Regression classifier (low complexity, avoids overfitting).
    5. Compute predicted probabilities p̂_i for every record.
    6. U = (1 / 2n) × Σ (p̂_i − 0.5)²

    Interpretation
    --------------
    U ≈ 0      → classifier cannot distinguish real from synthetic (high utility).
    U → 0.25   → perfect separation (poor utility).
    Accuracy ≈ 50% → indistinguishable (good synthetic data).

    Parameters
    ----------
    real_df              : original DataFrame.
    synthetic_df         : synthetic DataFrame (same schema).
    test_size            : fraction held out for out-of-sample evaluation (0 = no split).
    max_iter             : maximum LogReg solver iterations.
    return_probabilities : if True, include the full probability array in the output.

    Returns
    -------
    dict with keys:
        ``propensity_score_U``    – float  (main utility statistic, lower = better)
        ``accuracy_train``        – float  (in-sample accuracy)
        ``accuracy_test``         – float | None  (OOB accuracy when test_size > 0)
        ``n_original``            – int
        ``n_synthetic``           – int
        ``classifier``            – str
        ``class_report``          – str  (sklearn classification_report on test set)
        ``predicted_probabilities`` – list[float] | None  (if return_probabilities=True)
        ``note``                  – str  interpretation
    """
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, classification_report
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import LabelEncoder, StandardScaler

        # ── 1. Align & stack ─────────────────────────────────────────────────
        common_cols = [c for c in real_df.columns if c in synthetic_df.columns]
        if not common_cols:
            return {
                'propensity_score_U': None,
                'note': 'No common columns between real and synthetic data.',
            }

        real_sub  = real_df[common_cols].copy()
        synth_sub = synthetic_df[common_cols].copy()
        real_sub['_indicator']  = 0
        synth_sub['_indicator'] = 1
        stacked = pd.concat([real_sub, synth_sub], ignore_index=True)

        y = stacked['_indicator'].values
        X = stacked.drop(columns=['_indicator'])

        # ── 2. Encode / impute / scale ───────────────────────────────────────
        X_enc = X.copy()
        for col in X_enc.select_dtypes(include=['object', 'category']).columns:
            le = LabelEncoder()
            X_enc[col] = le.fit_transform(X_enc[col].astype(str))

        X_enc = X_enc.astype(float)
        for col in X_enc.columns:
            if X_enc[col].isna().any():
                X_enc[col] = X_enc[col].fillna(X_enc[col].median())

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_enc)

        # ── 3. Optional train / test split ───────────────────────────────────
        do_split = 0 < test_size < 1.0 and len(X_scaled) > 20
        if do_split:
            # Stratify to handle potential class imbalance gracefully
            try:
                X_train, X_test, y_train, y_test = train_test_split(
                    X_scaled, y, test_size=test_size, random_state=42, stratify=y
                )
            except ValueError:          # too few samples for stratify
                X_train, X_test, y_train, y_test = train_test_split(
                    X_scaled, y, test_size=test_size, random_state=42
                )
        else:
            X_train, y_train = X_scaled, y
            X_test,  y_test  = None, None

        # ── 4. Fit Logistic Regression ────────────────────────────────────────
        clf = LogisticRegression(
            C=1.0,
            max_iter=max_iter,
            solver='lbfgs',
            class_weight='balanced',    # handles class imbalance
            random_state=42,
        )
        clf.fit(X_train, y_train)

        # ── 5. Probabilities on full dataset ─────────────────────────────────
        # U is computed on the entire combined set (as per Woo et al.)
        p_hat = clf.predict_proba(X_scaled)[:, 1]     # P(synthetic)
        two_n = len(p_hat)
        U = float(np.sum((p_hat - 0.5) ** 2) / two_n)

        # ── 6. Accuracy metrics ───────────────────────────────────────────────
        acc_train = float(accuracy_score(y_train, clf.predict(X_train)))

        acc_test    = None
        class_rep   = None
        if do_split and X_test is not None:
            y_pred_test = clf.predict(X_test)
            acc_test    = float(accuracy_score(y_test, y_pred_test))
            class_rep   = classification_report(
                y_test, y_pred_test,
                target_names=['Real', 'Synthetic'],
                zero_division=0,
            )

        # ── 7. Interpret result ───────────────────────────────────────────────
        if U < 0.01:
            interp = 'U ≈ 0: excellent utility — classifier cannot distinguish real from synthetic.'
        elif U < 0.05:
            interp = 'U is low: good utility — distributions are similar.'
        elif U < 0.10:
            interp = 'U is moderate: acceptable utility — some distributional differences.'
        else:
            interp = 'U is high: poor utility — synthetic data is clearly distinguishable from real.'

        result: Dict = {
            'propensity_score_U': round(U, 6),
            'accuracy_train':     round(acc_train, 4),
            'accuracy_test':      round(acc_test, 4) if acc_test is not None else None,
            'n_original':         int(len(real_df)),
            'n_synthetic':        int(len(synthetic_df)),
            'classifier':         'LogisticRegression (C=1, lbfgs, balanced)',
            'class_report':       class_rep,
            'note':               interp,
        }

        if return_probabilities:
            result['predicted_probabilities'] = p_hat.tolist()

        return result

    except Exception as exc:
        logger.exception('compute_propensity_score_metric failed: %s', exc)
        return {
            'propensity_score_U': None,
            'note': f'Propensity metric computation skipped: {exc}',
        }


def plot_propensity_histogram(
    probabilities,
    title: str = 'Propensity Score Distribution',
    figsize: tuple = (9, 4),
    bins: int = 30,
    save_path: Optional[str] = None,
):
    """
    Histogram of predicted propensity probabilities P(synthetic).

    A well-performing synthetic dataset produces a histogram centred around 0.5
    (the classifier guesses at chance).  A bimodal distribution (peaks near 0
    and 1) indicates the two datasets are easily distinguishable.

    Parameters
    ----------
    probabilities : array-like of floats in [0, 1]
    title         : chart title
    figsize       : matplotlib figure size
    bins          : number of histogram bins
    save_path     : file path to save the figure; None → plt.show()

    Returns
    -------
    matplotlib.figure.Figure
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        logger.warning('matplotlib not installed – cannot produce propensity histogram.')
        return None

    probs = np.asarray(probabilities, dtype=float)
    if probs.size == 0:
        logger.warning('plot_propensity_histogram: empty probability array.')
        return None

    fig, ax = plt.subplots(figsize=figsize)

    # Colour each bar by whether it falls left (real-leaning) or right (synth-leaning) of 0.5
    counts, edges = np.histogram(probs, bins=bins, range=(0.0, 1.0))
    bar_width = edges[1] - edges[0]
    for i, (count, left) in enumerate(zip(counts, edges[:-1])):
        centre = left + bar_width / 2
        colour = '#667eea' if centre < 0.5 else '#f093fb'
        ax.bar(left, count, width=bar_width * 0.92, color=colour, alpha=0.85, align='edge')

    # Reference line at 0.5
    ax.axvline(x=0.5, color='#2c3e50', linestyle='--', linewidth=1.8, label='p = 0.5 (ideal centre)')

    # Mean line
    mean_p = float(np.mean(probs))
    ax.axvline(x=mean_p, color='#e74c3c', linestyle=':', linewidth=1.5, label=f'Mean = {mean_p:.3f}')

    patches = [
        mpatches.Patch(color='#667eea', label='P(synthetic) < 0.5  (classified as real)'),
        mpatches.Patch(color='#f093fb', label='P(synthetic) ≥ 0.5  (classified as synthetic)'),
    ]
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles=handles + patches, fontsize=8, loc='upper right')

    ax.set_xlim(0, 1)
    ax.set_xlabel('P(synthetic)', fontsize=11)
    ax.set_ylabel('Count', fontsize=11)
    ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
    ax.spines[['top', 'right']].set_visible(False)

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info('Propensity histogram saved to %s', save_path)
    else:
        plt.show()

    return fig


# ---------------------------------------------------------------------------
# Privacy proxy: Nearest-Neighbour Distance Ratio
# ---------------------------------------------------------------------------

def nearest_neighbor_distances(
    real_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    numeric_columns: List[str],
    k: int = 1,
) -> Dict:
    """Compute nearest-neighbour distances as a privacy proxy (NNDR)."""
    if not numeric_columns:
        return {'privacy_ratio': None, 'note': 'No numeric columns available'}

    numeric_cols = [c for c in numeric_columns if c in real_df.columns and c in synthetic_df.columns]
    if not numeric_cols:
        return {'privacy_ratio': None, 'note': 'Numeric columns not in both DataFrames'}

    try:
        from sklearn.neighbors import NearestNeighbors
        from sklearn.preprocessing import StandardScaler

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
        d_real_to_real = d_real_to_real[:, 1:]          # exclude self-match

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


# ---------------------------------------------------------------------------
# Privacy metric: CM3 (Canonical Correlation Confidentiality)
# ---------------------------------------------------------------------------

def _encode_and_scale(df: pd.DataFrame) -> np.ndarray:
    """
    Internal helper: encode categoricals via label encoding, impute missing
    values with column medians, and standardise to zero mean / unit variance.

    Returns a 2-D float numpy array safe for CCA.
    """
    from sklearn.preprocessing import LabelEncoder, StandardScaler

    encoded = df.copy()

    # Label-encode every non-numeric column
    for col in encoded.select_dtypes(include=["object", "category"]).columns:
        le = LabelEncoder()
        encoded[col] = le.fit_transform(encoded[col].astype(str))

    # Cast to float so arithmetic works uniformly
    encoded = encoded.astype(float)

    # Impute NaNs with column medians (avoids information leakage)
    for col in encoded.columns:
        if encoded[col].isna().any():
            median_val = encoded[col].median()
            encoded[col] = encoded[col].fillna(median_val)

    # Drop constant columns – CCA breaks on zero-variance features
    non_constant = encoded.columns[encoded.std() > 1e-9]
    encoded = encoded[non_constant]

    if encoded.empty:
        return np.empty((len(df), 0))

    scaler = StandardScaler()
    return scaler.fit_transform(encoded)


def _compute_cm2(
    X: np.ndarray,
    Y: np.ndarray,
    n_components: Optional[int] = None,
) -> float:
    """
    Compute CM2 for a pair of matrices using Canonical Correlation Analysis.

    CM2 = ∏_i (1 − ρ_i²)  where ρ_i are the canonical correlations.

    Interpretation:
      CM2 = 1  → X and Y are completely uncorrelated (high confidentiality).
      CM2 = 0  → X and Y are perfectly correlated (high disclosure risk).

    Parameters
    ----------
    X, Y        : 2-D float arrays of the same length (n_samples).
    n_components: number of CCA components to use; defaults to
                  min(rank(X), rank(Y), 10) to avoid excessive computation.

    Returns
    -------
    float in [0, 1]
    """
    from sklearn.cross_decomposition import CCA

    n_samples, p = X.shape
    q = Y.shape[1]

    # Edge cases: not enough features or samples for CCA
    if p == 0 or q == 0:
        logger.debug("_compute_cm2: empty feature matrix – returning CM2=1.0")
        return 1.0

    max_components = min(p, q, n_samples - 1)  # mathematical upper bound
    if max_components < 1:
        logger.debug("_compute_cm2: insufficient samples/features – returning CM2=1.0")
        return 1.0

    # Cap at 10 for performance; caller may override
    k = min(n_components or 10, max_components)

    try:
        cca = CCA(n_components=k, max_iter=500)
        cca.fit(X, Y)
        X_c, Y_c = cca.transform(X, Y)

        # Compute Pearson correlations between each canonical variate pair
        canonical_corrs = np.array([
            float(np.corrcoef(X_c[:, i], Y_c[:, i])[0, 1])
            for i in range(k)
        ])
        # Clip to [-1, 1] to handle floating-point artefacts
        canonical_corrs = np.clip(canonical_corrs, -1.0, 1.0)

        cm2 = float(np.prod(1.0 - canonical_corrs ** 2))
        # Ensure result is in [0, 1] despite any numerical noise
        cm2 = float(np.clip(cm2, 0.0, 1.0))
        return cm2

    except Exception as exc:
        logger.warning("_compute_cm2 failed (%s) – returning CM2=1.0", exc)
        return 1.0


def compute_cm3(
    real_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
) -> Dict:
    """
    Compute CM3 – Confidentiality Metric based on Canonical Correlation Analysis.

    Algorithm (Domingo-Ferrer & Torra, 2001)
    ----------------------------------------
    For each attribute j:
      1. Sort X (real) by column j     → X_sorted
      2. Sort Y (synthetic) by column j → Y_sorted
      3. Remove column j from both     → X_{−j},  Y_{−j}
      4. Compute CM2(X_{−j}, Y_{−j})  using canonical correlations

    CM3 = min_j CM2_j

    Interpretation
    --------------
    CM3 close to 1  →  high confidentiality (low disclosure risk)
    CM3 close to 0  →  low confidentiality  (high disclosure risk)

    Parameters
    ----------
    real_df      : original (real) DataFrame
    synthetic_df : synthetic DataFrame  (same schema)

    Returns
    -------
    dict with keys:
        ``cm3``          – float in [0, 1], the final CM3 score
        ``cm2_per_attr`` – dict mapping attribute name → CM2 score
        ``min_attr``     – attribute that yielded the minimum CM2
        ``note``         – interpretation string
    """
    try:
        # ── 1. Align on common columns only ──────────────────────────────────
        common_cols = [c for c in real_df.columns if c in synthetic_df.columns]
        if not common_cols:
            return {
                "cm3": None,
                "cm2_per_attr": {},
                "min_attr": None,
                "note": "No common columns between real and synthetic data.",
            }

        X_full = real_df[common_cols].reset_index(drop=True)
        Y_full = synthetic_df[common_cols].reset_index(drop=True)

        if len(common_cols) < 2:
            return {
                "cm3": None,
                "cm2_per_attr": {},
                "min_attr": None,
                "note": "CM3 requires at least 2 common columns.",
            }

        cm2_scores: Dict[str, float] = {}

        for j, col in enumerate(common_cols):
            logger.debug("CM3: processing attribute '%s' (%d/%d)", col, j + 1, len(common_cols))

            # ── 2. Sort both datasets by column j ────────────────────────────
            X_sorted = X_full.sort_values(by=col, na_position="last").reset_index(drop=True)
            Y_sorted = Y_full.sort_values(by=col, na_position="last").reset_index(drop=True)

            # ── 3. Remove column j ───────────────────────────────────────────
            remaining_cols = [c for c in common_cols if c != col]
            X_minus_j = X_sorted[remaining_cols]
            Y_minus_j = Y_sorted[remaining_cols]

            # ── 4. Encode, impute, scale ─────────────────────────────────────
            X_arr = _encode_and_scale(X_minus_j)
            Y_arr = _encode_and_scale(Y_minus_j)

            # Ensure same number of columns after constant-column removal
            # (both scalers may drop different columns; take intersection by index)
            min_cols = min(X_arr.shape[1], Y_arr.shape[1])
            if min_cols == 0:
                logger.debug("CM3: attribute '%s' – no usable features after encoding, skipping.", col)
                cm2_scores[col] = 1.0
                continue
            X_arr = X_arr[:, :min_cols]
            Y_arr = Y_arr[:, :min_cols]

            # ── 5. Compute CM2 ───────────────────────────────────────────────
            cm2 = _compute_cm2(X_arr, Y_arr)
            cm2_scores[col] = round(float(cm2), 6)

        if not cm2_scores:
            return {
                "cm3": None,
                "cm2_per_attr": {},
                "min_attr": None,
                "note": "Could not compute CM2 for any attribute.",
            }

        # ── 6. CM3 = minimum CM2 over all attributes ──────────────────────────
        min_attr = min(cm2_scores, key=cm2_scores.get)  # type: ignore[arg-type]
        cm3 = float(cm2_scores[min_attr])

        if cm3 >= 0.75:
            interpretation = "CM3 is high – strong confidentiality protection."
        elif cm3 >= 0.40:
            interpretation = "CM3 is moderate – acceptable confidentiality."
        else:
            interpretation = "CM3 is low – potential disclosure risk; review synthetic generation."

        return {
            "cm3": round(cm3, 6),
            "cm2_per_attr": cm2_scores,
            "min_attr": min_attr,
            "note": interpretation,
        }

    except Exception as exc:
        logger.exception("compute_cm3 failed: %s", exc)
        return {
            "cm3": None,
            "cm2_per_attr": {},
            "min_attr": None,
            "note": f"CM3 computation skipped: {exc}",
        }


def plot_cm2_barchart(
    cm2_per_attr: Dict[str, float],
    cm3_value: Optional[float] = None,
    title: str = "CM2 Scores per Attribute",
    figsize: tuple = (10, 5),
    save_path: Optional[str] = None,
):
    """
    Render a horizontal bar chart of CM2 scores for each attribute.

    Colour coding:
      Green  (CM2 ≥ 0.75) – high confidentiality
      Orange (0.40 ≤ CM2 < 0.75) – moderate
      Red    (CM2 < 0.40) – disclosure risk

    The minimum (i.e., CM3) is highlighted with a dashed vertical line.

    Parameters
    ----------
    cm2_per_attr : dict  {attribute_name: cm2_score}
    cm3_value    : optional float – drawn as a vertical reference line
    title        : chart title string
    figsize      : matplotlib figure size tuple
    save_path    : if provided, the chart is saved to this file path
                   (PNG/PDF/SVG depending on extension); otherwise plt.show()

    Returns
    -------
    matplotlib.figure.Figure  (so callers can embed it in a report)
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        logger.warning("matplotlib is not installed – cannot produce CM2 bar chart.")
        return None

    if not cm2_per_attr:
        logger.warning("plot_cm2_barchart: cm2_per_attr is empty – nothing to plot.")
        return None

    # Sort by CM2 ascending so the most-at-risk attribute is at the top
    attrs = list(cm2_per_attr.keys())
    scores = [cm2_per_attr[a] for a in attrs]
    sorted_pairs = sorted(zip(scores, attrs))          # ascending by CM2
    scores_sorted, attrs_sorted = zip(*sorted_pairs)

    # Assign colours by risk band
    colours = [
        "#2ecc71" if s >= 0.75 else ("#f39c12" if s >= 0.40 else "#e74c3c")
        for s in scores_sorted
    ]

    fig, ax = plt.subplots(figsize=figsize)
    bars = ax.barh(attrs_sorted, scores_sorted, color=colours, edgecolor="white", height=0.6)

    # Annotate bar ends with the numeric value
    for bar, score in zip(bars, scores_sorted):
        ax.text(
            bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
            f"{score:.4f}", va="center", ha="left", fontsize=9, color="#333333",
        )

    # Draw CM3 (min CM2) reference line
    if cm3_value is not None:
        ax.axvline(x=cm3_value, color="#2c3e50", linestyle="--", linewidth=1.5,
                   label=f"CM3 (min) = {cm3_value:.4f}")
        ax.legend(fontsize=9, loc="lower right")

    # Legend patches for colour meaning
    patches = [
        mpatches.Patch(color="#2ecc71", label="High confidentiality (≥ 0.75)"),
        mpatches.Patch(color="#f39c12", label="Moderate (0.40 – 0.75)"),
        mpatches.Patch(color="#e74c3c", label="Disclosure risk (< 0.40)"),
    ]
    ax.legend(handles=patches, fontsize=8, loc="lower right")

    ax.set_xlim(0, 1.15)
    ax.set_xlabel("CM2 Score", fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="y", labelsize=9)

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info("CM2 bar chart saved to %s", save_path)
    else:
        plt.show()

    return fig


# ---------------------------------------------------------------------------
# Main report generator
# ---------------------------------------------------------------------------

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
    """Generate a comprehensive utility and privacy metrics report."""
    from .identify import get_columns_by_role

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
        'propensity_score_utility': {},
        'propensity_metric': {},
        'privacy_proxy': {},
        'cm3_confidentiality': {},
        'notes': (
            'APEDP: DP-marginals (Laplace mechanism, ε-DP) + stratified permutation. '
            'Per-column utility metrics measure marginal distributional similarity. '
            'Propensity score utility (U) measures global/joint distributional similarity '
            '(U ≈ 0 = high utility, U → 0.25 = poor utility). '
            'CM3 measures confidentiality via canonical correlation (Domingo-Ferrer & Torra, 2001); '
            'CM3 close to 1 = high confidentiality, close to 0 = high disclosure risk.'
        ),
    }

    numeric_cols = [c for c in original_df.columns if pd.api.types.is_numeric_dtype(original_df[c])]

    # ── Per-column utility metrics ──────────────────────────────────────────
    utility_metrics: Dict = {}
    for col in original_df.columns:
        if col not in synthetic_df.columns:
            continue
        real_series = original_df[col]
        synthetic_series = synthetic_df[col]
        col_metrics: Dict = {}
        try:
            if not pd.api.types.is_numeric_dtype(real_series):
                col_metrics['total_variation_distance'] = float(
                    total_variation_distance(real_series, synthetic_series)
                )
            else:
                col_metrics['kolmogorov_smirnov'] = float(
                    kolmogorov_smirnov_statistic(real_series, synthetic_series)
                )
        except Exception:
            pass
        col_metrics['missingness'] = missingness_comparison(real_series, synthetic_series)
        utility_metrics[col] = col_metrics

    report['utility_metrics'] = utility_metrics

    # ── Global utility: propensity score (legacy lightweight) ──────────────
    report['propensity_score_utility'] = propensity_score_utility(original_df, synthetic_df)

    # ── Enhanced propensity score metric ────────────────────────────────────
    try:
        report['propensity_metric'] = compute_propensity_score_metric(
            original_df, synthetic_df, test_size=0.2
        )
    except Exception as e:
        report['propensity_metric'] = {
            'propensity_score_U': None,
            'note': f'Propensity metric skipped: {e}',
        }

    # ── Privacy proxy: nearest-neighbour distance ratio ────────────────────
    try:
        report['privacy_proxy'] = nearest_neighbor_distances(original_df, synthetic_df, numeric_cols)
    except Exception as e:
        report['privacy_proxy'] = {'note': f'Skipped: {e}'}

    # ── CM3 confidentiality metric ──────────────────────────────────────────
    try:
        report['cm3_confidentiality'] = compute_cm3(original_df, synthetic_df)
    except Exception as e:
        report['cm3_confidentiality'] = {
            'cm3': None,
            'cm2_per_attr': {},
            'min_attr': None,
            'note': f'CM3 skipped: {e}',
        }

    return report
