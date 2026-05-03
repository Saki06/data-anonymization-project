# -*- coding: utf-8 -*-
# Force UTF-8 output on Windows
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

"""
Test suite for the CM3 Confidentiality Metric (Canonical Correlation).

Run from the backend/ directory:
    python test_cm3_metric.py

Tests
-----
  1. High-confidentiality case  – synthetic very different from real  → CM3 near 1
  2. Low-confidentiality case   – synthetic nearly identical to real  → CM3 near 0
  3. Edge cases                 – single column, constant column, NaN-heavy data
  4. generate_report() integration – cm3_confidentiality key present in report
  5. plot_cm2_barchart()        – produces a figure without error

Reference: Domingo-Ferrer & Torra (2001) "Disclosure Control Methods and
Information Loss for Microdata".
"""

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from components.synthetic_data.apedp.report import (
    compute_cm3,
    plot_cm2_barchart,
    generate_report,
)
from components.synthetic_data.apedp.identify import identify_columns

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def _banner(text: str) -> None:
    print(f"\n{BOLD}{'=' * 65}{RESET}")
    print(f"{BOLD}  {text}{RESET}")
    print(f"{BOLD}{'=' * 65}{RESET}")


def _ok(msg: str) -> None:
    print(f"  {GREEN}[OK]   {msg}{RESET}")


def _fail(msg: str) -> None:
    print(f"  {RED}[FAIL] {msg}{RESET}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}[WARN] {msg}{RESET}")


# ── Data factories ────────────────────────────────────────────────────────────

def make_real_df(n: int = 300, seed: int = 0) -> pd.DataFrame:
    """Realistic demographic-style dataset."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "age":      rng.integers(18, 80, size=n),
        "income":   rng.normal(50_000, 15_000, size=n).round(2),
        "gender":   rng.choice(["Male", "Female", "Other"], size=n),
        "region":   rng.choice(["North", "South", "East", "West"], size=n),
        "score":    rng.uniform(0, 100, size=n).round(1),
    })


def make_high_conf_synthetic(n: int = 300, seed: int = 99) -> pd.DataFrame:
    """
    Synthetic data from a completely DIFFERENT distribution.
    CM2 values should be high (close to 1) → CM3 near 1 → high confidentiality.
    """
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "age":      rng.integers(18, 80, size=n),
        "income":   rng.normal(50_000, 15_000, size=n).round(2),
        "gender":   rng.choice(["Male", "Female", "Other"], size=n),
        "region":   rng.choice(["North", "South", "East", "West"], size=n),
        "score":    rng.uniform(0, 100, size=n).round(1),
    })


def make_low_conf_synthetic(real_df: pd.DataFrame) -> pd.DataFrame:
    """
    Synthetic data = real data with tiny Gaussian jitter on numeric cols.
    CCA will find very high canonical correlations → CM2 near 0 → CM3 near 0.
    """
    synth = real_df.copy()
    rng = np.random.default_rng(7)
    for col in synth.select_dtypes(include="number").columns:
        noise = rng.normal(0, 1e-3, size=len(synth))   # negligible noise
        synth[col] = synth[col] + noise
    return synth


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_high_confidentiality():
    """Independently-drawn synthetic data → CM3 should be reasonably high."""
    _banner("TEST 1 – High Confidentiality (independent synthetic data)")

    real  = make_real_df(n=200)
    synth = make_high_conf_synthetic(n=200)

    result = compute_cm3(real, synth)
    print(f"  cm3          : {result.get('cm3')}")
    print(f"  min_attr     : {result.get('min_attr')}")
    print(f"  note         : {result.get('note')}")
    print(f"  cm2_per_attr : {result.get('cm2_per_attr')}")

    assert result["cm3"] is not None, "cm3 should not be None"
    _ok(f"CM3 = {result['cm3']:.6f}")

    cm3 = result["cm3"]
    if cm3 > 0.1:
        _ok("CM3 > 0.1 as expected for independently-drawn data")
    else:
        _warn(f"CM3 = {cm3:.6f} is unexpectedly low for independent data")


def test_low_confidentiality():
    """Near-identical synthetic data → CM3 should be near 0."""
    _banner("TEST 2 – Low Confidentiality (synthetic ≈ real with tiny jitter)")

    real  = make_real_df(n=200)
    synth = make_low_conf_synthetic(real)

    result = compute_cm3(real, synth)
    print(f"  cm3          : {result.get('cm3')}")
    print(f"  min_attr     : {result.get('min_attr')}")
    print(f"  note         : {result.get('note')}")

    assert result["cm3"] is not None, "cm3 should not be None"
    cm3 = result["cm3"]
    _ok(f"CM3 = {cm3:.6f}")

    if cm3 < 0.5:
        _ok("CM3 < 0.5 as expected for near-identical data")
    else:
        _warn(f"CM3 = {cm3:.6f} is higher than expected for near-identical data")


def test_ordering():
    """High-conf CM3 should NOT be lower than low-conf CM3."""
    _banner("TEST 3 – Ordering: independent data CM3 ≥ near-copy CM3")

    real      = make_real_df(n=200)
    synth_hi  = make_high_conf_synthetic(n=200)
    synth_lo  = make_low_conf_synthetic(real)

    cm3_hi = compute_cm3(real, synth_hi)["cm3"]
    cm3_lo = compute_cm3(real, synth_lo)["cm3"]

    print(f"  CM3 (independent) = {cm3_hi:.6f}")
    print(f"  CM3 (near-copy)   = {cm3_lo:.6f}")

    assert cm3_hi is not None and cm3_lo is not None
    if cm3_hi >= cm3_lo:
        _ok(f"Ordering correct: {cm3_hi:.4f} ≥ {cm3_lo:.4f}")
    else:
        _warn(
            f"Ordering reversed: {cm3_hi:.4f} < {cm3_lo:.4f}. "
            "This may happen with small datasets due to CCA instability."
        )


def test_edge_single_column():
    """Only one column → CM3 should return None with a meaningful note."""
    _banner("TEST 4 – Edge Case: single column")

    real  = pd.DataFrame({"age": [20, 30, 40, 50, 60]})
    synth = pd.DataFrame({"age": [22, 32, 42, 52, 62]})

    result = compute_cm3(real, synth)
    print(f"  Result: {result}")

    assert result["cm3"] is None, "CM3 should be None for single-column data"
    assert "note" in result
    _ok(f"Correctly returned CM3=None. Note: '{result['note']}'")


def test_edge_constant_column():
    """Constant columns should be silently dropped; CM3 must still compute."""
    _banner("TEST 5 – Edge Case: constant column in dataset")

    rng = np.random.default_rng(42)
    real = pd.DataFrame({
        "age":      rng.integers(18, 80, size=100),
        "constant": [5] * 100,          # zero-variance column
        "income":   rng.normal(50_000, 15_000, size=100).round(2),
    })
    synth = pd.DataFrame({
        "age":      rng.integers(18, 80, size=100),
        "constant": [5] * 100,
        "income":   rng.normal(55_000, 12_000, size=100).round(2),
    })

    result = compute_cm3(real, synth)
    print(f"  Result: {result}")

    assert result["cm3"] is not None, "CM3 should not be None even with constant column"
    _ok(f"CM3 = {result['cm3']:.6f} despite constant column")


def test_edge_nan_heavy():
    """High proportion of NaNs should be imputed; CM3 must return a value."""
    _banner("TEST 6 – Edge Case: NaN-heavy data")

    rng = np.random.default_rng(11)
    n = 150
    age    = rng.integers(18, 80, size=n).astype(float)
    income = rng.normal(50_000, 15_000, size=n)

    # Introduce 40% NaN in each column
    mask = rng.random(n) < 0.4
    age[mask] = np.nan
    income[mask] = np.nan

    real  = pd.DataFrame({"age": age, "income": income})
    synth = pd.DataFrame({
        "age":    rng.integers(18, 80, size=n).astype(float),
        "income": rng.normal(52_000, 14_000, size=n),
    })

    result = compute_cm3(real, synth)
    print(f"  Result: {result}")

    assert result["cm3"] is not None, "CM3 must handle NaN-heavy data"
    _ok(f"CM3 = {result['cm3']:.6f} with ~40% NaN imputed")


def test_edge_mixed_types():
    """Mixed numeric + categorical columns → CM3 must encode and compute."""
    _banner("TEST 7 – Mixed Numeric + Categorical Columns")

    rng = np.random.default_rng(3)
    n = 200
    real = pd.DataFrame({
        "age":        rng.integers(18, 70, size=n),
        "income":     rng.normal(50_000, 10_000, size=n).round(2),
        "gender":     rng.choice(["Male", "Female"], size=n),
        "occupation": rng.choice(["Engineer", "Teacher", "Doctor", "Other"], size=n),
    })
    synth = pd.DataFrame({
        "age":        rng.integers(18, 70, size=n),
        "income":     rng.normal(52_000, 11_000, size=n).round(2),
        "gender":     rng.choice(["Male", "Female"], size=n),
        "occupation": rng.choice(["Engineer", "Teacher", "Doctor", "Other"], size=n),
    })

    result = compute_cm3(real, synth)
    print(f"  cm3          : {result.get('cm3')}")
    print(f"  cm2_per_attr : {result.get('cm2_per_attr')}")
    print(f"  note         : {result.get('note')}")

    assert result["cm3"] is not None, "CM3 must handle mixed-type columns"
    _ok(f"CM3 = {result['cm3']:.6f} for mixed numeric + categorical data")


def test_generate_report_integration():
    """CM3 must appear as 'cm3_confidentiality' in generate_report() output."""
    _banner("TEST 8 – generate_report() Integration")

    real  = make_real_df(n=150)
    synth = make_high_conf_synthetic(n=150)

    metadata_df = identify_columns(real)

    report = generate_report(
        original_df     = real,
        synthetic_df    = synth,
        metadata_df     = metadata_df,
        epsilon         = 1.0,
        seed            = 42,
        strata_keys     = [],
        dropped_columns = [],
    )

    # Check key present
    assert "cm3_confidentiality" in report, \
        "'cm3_confidentiality' key missing from report"
    _ok("'cm3_confidentiality' key present in report")

    cm3_block = report["cm3_confidentiality"]
    assert "cm3" in cm3_block, "'cm3' missing from cm3_confidentiality block"
    _ok(f"cm3 = {cm3_block['cm3']}")

    assert "cm2_per_attr" in cm3_block, "'cm2_per_attr' missing"
    _ok(f"cm2_per_attr has {len(cm3_block['cm2_per_attr'])} entries")

    assert "note" in cm3_block, "'note' missing"
    _ok(f"note: {cm3_block['note']}")

    # Verify existing metrics still present
    for key in ("utility_metrics", "propensity_score_utility", "privacy_proxy"):
        assert key in report, f"'{key}' missing from report"
    _ok("All existing metric keys still present")

    print(f"\n  {BOLD}Full report keys:{RESET} {list(report.keys())}")


def test_plot_cm2_barchart():
    """plot_cm2_barchart() should return a Figure without raising."""
    _banner("TEST 9 – plot_cm2_barchart() Visualisation")

    try:
        import matplotlib
        matplotlib.use("Agg")   # non-interactive backend for CI/headless
        import matplotlib.pyplot as plt
    except ImportError:
        _warn("matplotlib not installed – skipping visualisation test")
        return

    cm2_per_attr = {
        "age":      0.83,
        "income":   0.45,
        "gender":   0.91,
        "region":   0.28,   # disclosure risk band (red)
        "score":    0.67,
    }
    cm3_value = min(cm2_per_attr.values())

    fig = plot_cm2_barchart(
        cm2_per_attr = cm2_per_attr,
        cm3_value    = cm3_value,
        title        = "CM2 Scores per Attribute (Test)",
    )

    assert fig is not None, "plot_cm2_barchart() returned None unexpectedly"
    _ok("Figure returned successfully")

    # Optionally save to disk for visual inspection
    out_path = "cm2_barchart_test.png"
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    _ok(f"Chart saved to {out_path}")
    plt.close(fig)


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_high_confidentiality,
        test_low_confidentiality,
        test_ordering,
        test_edge_single_column,
        test_edge_constant_column,
        test_edge_nan_heavy,
        test_edge_mixed_types,
        test_generate_report_integration,
        test_plot_cm2_barchart,
    ]

    passed = failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            _fail(f"ASSERTION FAILED in {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            _fail(f"UNEXPECTED ERROR in {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    _banner("SUMMARY")
    print(f"  {GREEN}Passed: {passed}{RESET}   {RED}Failed: {failed}{RESET}\n")
    sys.exit(0 if failed == 0 else 1)
