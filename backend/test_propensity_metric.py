# -*- coding: utf-8 -*-
# Force UTF-8 output on Windows
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

"""
Quick test for the propensity_score_utility metric added to report.py.

Run from the backend/ directory:
    python test_propensity_metric.py

Tests:
  1. High-utility case  – synthetic ≈ real      → U should be near 0
  2. Low-utility case   – synthetic very different → U should be notably > 0
  3. Full generate_report() integration           → key present in report dict
"""

import sys
import numpy as np
import pandas as pd

# Make sure the backend package is importable
sys.path.insert(0, ".")

from components.synthetic_data.apedp.report import (
    propensity_score_utility,
    generate_report,
)
from components.synthetic_data.apedp.identify import identify_columns

# ─── ANSI colours for readability ────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def _banner(text: str) -> None:
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  {text}{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")


def _ok(msg: str) -> None:
    print(f"  {GREEN}[OK]  {msg}{RESET}")


def _fail(msg: str) -> None:
    print(f"  {RED}[FAIL]  {msg}{RESET}")


# ─── Test data factories ──────────────────────────────────────────────────────

def make_real_df(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "age":    rng.integers(18, 80, size=n),
        "income": rng.normal(50_000, 15_000, size=n).round(2),
        "gender": rng.choice(["Male", "Female", "Other"], size=n),
        "region": rng.choice(["North", "South", "East", "West"], size=n),
    })


def make_high_utility_df(real_df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Synthetic data drawn from the same distribution → high utility (U ≈ 0)."""
    rng = np.random.default_rng(seed)
    n = len(real_df)
    return pd.DataFrame({
        "age":    rng.integers(18, 80, size=n),
        "income": rng.normal(50_000, 15_000, size=n).round(2),
        "gender": rng.choice(["Male", "Female", "Other"], size=n),
        "region": rng.choice(["North", "South", "East", "West"], size=n),
    })


def make_low_utility_df(n: int = 300, seed: int = 7) -> pd.DataFrame:
    """Synthetic data from a very different distribution → low utility (U >> 0)."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "age":    rng.integers(60, 90, size=n),           # shifted distribution
        "income": rng.normal(200_000, 5_000, size=n).round(2),  # very different
        "gender": rng.choice(["Male"], size=n),           # constant, no diversity
        "region": rng.choice(["Overseas"], size=n),       # unseen category
    })


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_high_utility():
    _banner("TEST 1 - High Utility Case (synthetic ~= real)")
    real    = make_real_df()
    synth   = make_high_utility_df(real)
    result  = propensity_score_utility(real, synth)

    print(f"  Result : {result}")
    U = result.get("propensity_score_U")

    assert U is not None, "propensity_score_U should not be None"
    _ok(f"propensity_score_U = {U:.6f}  (expected close to 0)")

    if U < 0.05:
        _ok("U < 0.05 -> classifier cannot distinguish -> GOOD UTILITY")
    else:
        print(f"  {YELLOW}[WARN]  U = {U:.6f} is higher than expected for matching distributions.{RESET}")


def test_low_utility():
    _banner("TEST 2 - Low Utility Case (synthetic very different from real)")
    real    = make_real_df()
    synth   = make_low_utility_df()
    result  = propensity_score_utility(real, synth)

    print(f"  Result : {result}")
    U = result.get("propensity_score_U")

    assert U is not None, "propensity_score_U should not be None"
    _ok(f"propensity_score_U = {U:.6f}  (expected >> 0)")

    if U > 0.05:
        _ok("U > 0.05 -> classifier separates easily -> POOR UTILITY (as expected)")
    else:
        print(f"  {YELLOW}[WARN]  U = {U:.6f} lower than expected - distributions may be too similar.{RESET}")


def test_ordering():
    _banner("TEST 3 - Ordering: High-Utility U < Low-Utility U")
    real        = make_real_df()
    synth_good  = make_high_utility_df(real)
    synth_bad   = make_low_utility_df()

    U_good = propensity_score_utility(real, synth_good)["propensity_score_U"]
    U_bad  = propensity_score_utility(real, synth_bad)["propensity_score_U"]

    print(f"  U (high utility) = {U_good:.6f}")
    print(f"  U (low  utility) = {U_bad:.6f}")

    assert U_good < U_bad, f"Expected U_good ({U_good}) < U_bad ({U_bad})"
    _ok("Ordering correct: similar data has lower U than dissimilar data")


def test_generate_report_integration():
    _banner("TEST 4 – generate_report() Integration")
    real  = make_real_df()
    synth = make_high_utility_df(real)

    # Build the metadata DataFrame that generate_report expects
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

    # Check top-level keys
    assert "propensity_score_utility" in report, \
        "propensity_score_utility key missing from report"
    _ok("propensity_score_utility key present in report")

    psu = report["propensity_score_utility"]
    assert "propensity_score_U" in psu, \
        "propensity_score_U missing from propensity_score_utility block"
    _ok(f"propensity_score_U = {psu['propensity_score_U']}")

    # Check existing metrics still present
    assert "utility_metrics" in report,  "utility_metrics missing"
    assert "privacy_proxy"   in report,  "privacy_proxy missing"
    _ok("Existing metrics (utility_metrics, privacy_proxy) still present")

    print(f"\n  {BOLD}Full report keys:{RESET} {list(report.keys())}")


# ─── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    passed = 0
    failed = 0

    tests = [test_high_utility, test_low_utility, test_ordering, test_generate_report_integration]
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            _fail(f"ASSERTION FAILED: {e}")
            failed += 1
        except Exception as e:
            _fail(f"UNEXPECTED ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    _banner("SUMMARY")
    print(f"  {GREEN}Passed: {passed}{RESET}   {RED}Failed: {failed}{RESET}\n")
    sys.exit(0 if failed == 0 else 1)
