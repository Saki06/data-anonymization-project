# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

"""
Test suite for compute_propensity_score_metric and plot_propensity_histogram.

Run from the backend/ directory:
    python test_propensity_score_metric.py

Tests
-----
  1. High utility  – synthetic drawn from same distribution → U near 0, accuracy ~50%
  2. Low utility   – synthetic from very different distribution → U >> 0, accuracy > 70%
  3. Ordering      – high-utility U < low-utility U
  4. Return probs  – return_probabilities=True includes list of floats
  5. No split      – test_size=0 skips train/test split gracefully
  6. Edge cases    – constant columns, NaN-heavy data, single column
  7. generate_report() integration – 'propensity_metric' key present in report
  8. plot_propensity_histogram() – returns a Figure without error
"""

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from components.synthetic_data.apedp.report import (
    compute_propensity_score_metric,
    plot_propensity_histogram,
    generate_report,
)
from components.synthetic_data.apedp.identify import identify_columns

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def _banner(text):
    print(f"\n{BOLD}{'=' * 65}{RESET}")
    print(f"{BOLD}  {text}{RESET}")
    print(f"{BOLD}{'=' * 65}{RESET}")

def _ok(msg):   print(f"  {GREEN}[OK]   {msg}{RESET}")
def _fail(msg): print(f"  {RED}[FAIL] {msg}{RESET}")
def _warn(msg): print(f"  {YELLOW}[WARN] {msg}{RESET}")


# ── Data factories ─────────────────────────────────────────────────────────────

def make_real_df(n=300, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "age":    rng.integers(18, 80, size=n),
        "income": rng.normal(50_000, 15_000, size=n).round(2),
        "gender": rng.choice(["Male", "Female", "Other"], size=n),
        "region": rng.choice(["North", "South", "East", "West"], size=n),
    })


def make_high_utility_df(n=300, seed=42):
    """Independent draw from same distribution → should be indistinguishable."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "age":    rng.integers(18, 80, size=n),
        "income": rng.normal(50_000, 15_000, size=n).round(2),
        "gender": rng.choice(["Male", "Female", "Other"], size=n),
        "region": rng.choice(["North", "South", "East", "West"], size=n),
    })


def make_low_utility_df(n=300, seed=7):
    """Very different distribution → easy to separate → high U."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "age":    rng.integers(60, 90, size=n),
        "income": rng.normal(200_000, 5_000, size=n).round(2),
        "gender": rng.choice(["Male"], size=n),
        "region": rng.choice(["Overseas"], size=n),
    })


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_high_utility():
    _banner("TEST 1 – High Utility (same distribution)")
    real  = make_real_df()
    synth = make_high_utility_df()
    result = compute_propensity_score_metric(real, synth)

    print(f"  propensity_score_U : {result.get('propensity_score_U')}")
    print(f"  accuracy_train     : {result.get('accuracy_train')}")
    print(f"  accuracy_test      : {result.get('accuracy_test')}")
    print(f"  note               : {result.get('note')}")

    assert result["propensity_score_U"] is not None, "U must not be None"
    _ok(f"U = {result['propensity_score_U']:.6f}")

    U = result["propensity_score_U"]
    if U < 0.05:
        _ok("U < 0.05 → good utility as expected")
    else:
        _warn(f"U = {U:.4f} is higher than 0.05; distributions may differ slightly")

    acc_test = result.get("accuracy_test")
    if acc_test is not None:
        _ok(f"Test accuracy = {acc_test*100:.1f}%  (ideal ≈ 50%)")
    else:
        _warn("No test accuracy returned (split may have been skipped)")


def test_low_utility():
    _banner("TEST 2 – Low Utility (very different distribution)")
    real  = make_real_df()
    synth = make_low_utility_df()
    result = compute_propensity_score_metric(real, synth)

    print(f"  propensity_score_U : {result.get('propensity_score_U')}")
    print(f"  accuracy_train     : {result.get('accuracy_train')}")
    print(f"  accuracy_test      : {result.get('accuracy_test')}")
    print(f"  note               : {result.get('note')}")

    assert result["propensity_score_U"] is not None
    U = result["propensity_score_U"]
    _ok(f"U = {U:.6f}")

    if U > 0.05:
        _ok("U > 0.05 → poor utility as expected (distributions differ)")
    else:
        _warn(f"U = {U:.4f} unexpectedly low for very different distributions")


def test_ordering():
    _banner("TEST 3 – Ordering: U(high-utility) < U(low-utility)")
    real      = make_real_df()
    synth_hi  = make_high_utility_df()
    synth_lo  = make_low_utility_df()

    U_hi = compute_propensity_score_metric(real, synth_hi)["propensity_score_U"]
    U_lo = compute_propensity_score_metric(real, synth_lo)["propensity_score_U"]

    print(f"  U (high-utility) = {U_hi:.6f}")
    print(f"  U (low-utility)  = {U_lo:.6f}")

    assert U_hi is not None and U_lo is not None
    assert U_hi < U_lo, f"Expected U_hi ({U_hi}) < U_lo ({U_lo})"
    _ok(f"Ordering correct: {U_hi:.4f} < {U_lo:.4f}")


def test_return_probabilities():
    _banner("TEST 4 – return_probabilities=True")
    real  = make_real_df(n=100)
    synth = make_high_utility_df(n=100)
    result = compute_propensity_score_metric(real, synth, return_probabilities=True)

    assert "predicted_probabilities" in result, "'predicted_probabilities' key missing"
    probs = result["predicted_probabilities"]
    assert isinstance(probs, list), "predicted_probabilities must be a list"
    assert len(probs) == 200, f"Expected 200 probs, got {len(probs)}"
    assert all(0.0 <= p <= 1.0 for p in probs), "All probabilities must be in [0, 1]"
    _ok(f"{len(probs)} probabilities returned, all in [0,1]")
    _ok(f"Mean P(synthetic) = {sum(probs)/len(probs):.4f}  (ideal ≈ 0.5)")


def test_no_split():
    _banner("TEST 5 – test_size=0 (no train/test split)")
    real  = make_real_df(n=100)
    synth = make_high_utility_df(n=100)
    result = compute_propensity_score_metric(real, synth, test_size=0)

    assert result["propensity_score_U"] is not None
    assert result.get("accuracy_test") is None, "accuracy_test should be None when test_size=0"
    assert result.get("class_report") is None,  "class_report should be None when test_size=0"
    _ok(f"U = {result['propensity_score_U']:.6f}, accuracy_test = None as expected")


def test_edge_constant_column():
    _banner("TEST 6a – Edge Case: constant column")
    rng = np.random.default_rng(1)
    n = 100
    real  = pd.DataFrame({"age": rng.integers(18, 80, size=n), "constant": [5]*n})
    synth = pd.DataFrame({"age": rng.integers(18, 80, size=n), "constant": [5]*n})

    result = compute_propensity_score_metric(real, synth)
    assert result["propensity_score_U"] is not None
    _ok(f"U = {result['propensity_score_U']:.6f} despite constant column")


def test_edge_nan_heavy():
    _banner("TEST 6b – Edge Case: NaN-heavy data")
    rng = np.random.default_rng(2)
    n = 150
    age  = rng.integers(18, 80, size=n).astype(float)
    inc  = rng.normal(50_000, 15_000, size=n)
    mask = rng.random(n) < 0.4
    age[mask] = np.nan
    inc[mask] = np.nan

    real  = pd.DataFrame({"age": age, "income": inc})
    synth = pd.DataFrame({"age": rng.integers(18, 80, size=n).astype(float),
                          "income": rng.normal(52_000, 14_000, size=n)})

    result = compute_propensity_score_metric(real, synth)
    assert result["propensity_score_U"] is not None
    _ok(f"U = {result['propensity_score_U']:.6f} with ~40% NaN imputed")


def test_edge_single_column():
    _banner("TEST 6c – Edge Case: single column (should still work)")
    rng = np.random.default_rng(3)
    real  = pd.DataFrame({"age": rng.integers(18, 80, size=50)})
    synth = pd.DataFrame({"age": rng.integers(18, 80, size=50)})

    result = compute_propensity_score_metric(real, synth)
    assert result["propensity_score_U"] is not None
    _ok(f"U = {result['propensity_score_U']:.6f} for single-column dataset")


def test_class_report_present():
    _banner("TEST 7 – class_report in output (with train/test split)")
    real  = make_real_df(n=200)
    synth = make_low_utility_df(n=200)
    result = compute_propensity_score_metric(real, synth, test_size=0.2)

    assert "class_report" in result, "'class_report' key missing"
    if result["class_report"] is not None:
        assert "Real" in result["class_report"] or "Synthetic" in result["class_report"], \
            "class_report should mention Real/Synthetic"
        _ok("class_report present and contains expected labels")
    else:
        _warn("class_report is None (may be expected for tiny datasets)")


def test_generate_report_integration():
    _banner("TEST 8 – generate_report() Integration")
    real  = make_real_df(n=150)
    synth = make_high_utility_df(n=150)

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

    assert "propensity_metric" in report, "'propensity_metric' key missing from report"
    _ok("'propensity_metric' key present in report")

    pm = report["propensity_metric"]
    assert "propensity_score_U" in pm,  "'propensity_score_U' missing"
    assert "accuracy_train"     in pm,  "'accuracy_train' missing"
    assert "accuracy_test"      in pm,  "'accuracy_test' missing"
    assert "note"               in pm,  "'note' missing"
    _ok(f"U = {pm['propensity_score_U']}  |  train_acc = {pm['accuracy_train']}  |  test_acc = {pm['accuracy_test']}")
    _ok(f"note: {pm['note']}")

    for key in ("utility_metrics", "propensity_score_utility", "privacy_proxy", "cm3_confidentiality"):
        assert key in report, f"'{key}' missing from report"
    _ok("All existing metric keys still present")

    print(f"\n  {BOLD}Full report keys:{RESET} {list(report.keys())}")


def test_plot_propensity_histogram():
    _banner("TEST 9 – plot_propensity_histogram()")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        _warn("matplotlib not installed – skipping visualisation test")
        return

    # Generate some realistic probabilities centred around 0.5
    rng = np.random.default_rng(0)
    probs = np.clip(rng.normal(0.5, 0.15, 600), 0, 1).tolist()

    fig = plot_propensity_histogram(probs, title="Test – Propensity Distribution")
    assert fig is not None, "plot_propensity_histogram() returned None"
    _ok("Figure returned successfully")

    out = "propensity_histogram_test.png"
    fig.savefig(out, dpi=100, bbox_inches="tight")
    _ok(f"Chart saved to {out}")
    plt.close(fig)


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_high_utility,
        test_low_utility,
        test_ordering,
        test_return_probabilities,
        test_no_split,
        test_edge_constant_column,
        test_edge_nan_heavy,
        test_edge_single_column,
        test_class_report_present,
        test_generate_report_integration,
        test_plot_propensity_histogram,
    ]

    passed = failed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            _fail(f"ASSERTION FAILED in {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            _fail(f"UNEXPECTED ERROR in {fn.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    _banner("SUMMARY")
    print(f"  {GREEN}Passed: {passed}{RESET}   {RED}Failed: {failed}{RESET}\n")
    sys.exit(0 if failed == 0 else 1)
