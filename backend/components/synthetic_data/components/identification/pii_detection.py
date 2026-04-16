"""
PII and role detection for Component 01.

This module reuses the legacy heuristics from `apedp.identify` and
extends them with data-driven checks:
- uniqueness_ratio and cardinality
- regex based detection for email/phone/NIC/passport/address-like
- DOB/date-like detection

The main entry point is `build_metadata`, which returns a
`DatasetMetadata` object.
"""

from __future__ import annotations

from typing import Dict, List
import re

import pandas as pd
from .metadata import ColumnInfo, ColumnStats, DatasetMetadata


EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[- ]?)?(?:\d{9,12})\b")
NIC_REGEX = re.compile(r"\b(?:\d{9}[vVxX]|\d{12})\b")
PASSPORT_REGEX = re.compile(r"\b[A-Z]{1,2}\d{6,8}\b")
DATE_LIKE_COLNAME = re.compile(r"(dob|date[_ ]?of[_ ]?birth|birth[_ ]?date)", re.IGNORECASE)


def _detect_pii_like(series: pd.Series) -> List[str]:
    """Return list of detected PII pattern types for a Series."""
    flags: List[str] = []
    if not (series.dtype == "O" or pd.api.types.is_string_dtype(series)):
        return flags

    sample = series.dropna().astype(str).head(500)
    text = " ".join(sample.tolist())

    if EMAIL_REGEX.search(text):
        flags.append("email")
    if PHONE_REGEX.search(text):
        flags.append("phone")
    if NIC_REGEX.search(text):
        flags.append("nic")
    if PASSPORT_REGEX.search(text):
        flags.append("passport")

    # Heuristic: very long strings that might contain addresses
    if any(len(x) > 60 for x in sample if isinstance(x, str)):
        flags.append("address_like")

    return flags


def _is_date_like(col_name: str, series: pd.Series) -> bool:
    """Detect DOB/date-like columns using name and parseability."""
    if DATE_LIKE_COLNAME.search(col_name):
        return True
    sample = series.dropna().head(200)
    if sample.empty:
        return False
    try:
        date_format = "%Y-%m-%d"
        parsed = pd.to_datetime(sample, errors="coerce", format=date_format)
        return bool(parsed.notna().mean() > 0.7)
    except Exception:
        try:
            parsed = pd.to_datetime(sample, errors="coerce")
            return bool(parsed.notna().mean() > 0.7)
        except Exception:
            return False


def _legacy_identify_columns_local(df: pd.DataFrame) -> pd.DataFrame:
    """
    Minimal legacy-like classifier used internally to seed roles
    without importing apedp.identify (prevents circular imports).
    Returns DataFrame with columns: ['column','role'].
    """
    rows = []
    n = max(len(df), 1)

    for col in df.columns:
        s = df[col]
        role = "Non-sensitive"

        pii_types = _detect_pii_like(s)
        if any(t in pii_types for t in ("email", "phone", "nic", "passport")):
            role = "Direct Identifier"
        elif _is_date_like(col.lower(), s):
            role = "Quasi-identifier"
        else:
            uniq_ratio = (s.nunique(dropna=True) / n) if n else 0.0
            if uniq_ratio > 0.98:
                role = "Quasi-identifier"

        lname = col.lower()
        if any(k in lname for k in ("income", "salary", "wage", "disease", "religion", "ethnic", "politic")):
            role = "Sensitive"

        rows.append({"column": col, "role": role})

    return pd.DataFrame(rows)


def build_metadata(df: pd.DataFrame) -> DatasetMetadata:
    """
    Build a `DatasetMetadata` object from a DataFrame.

    This function is the canonical way Component 01 describes datasets
    to later components.
    """
    legacy_md = _legacy_identify_columns_local(df)

    columns: Dict[str, ColumnInfo] = {}
    direct_ids: List[str] = []
    quasi_ids: List[str] = []
    sensitive: List[str] = []
    non_sensitive: List[str] = []

    n_rows = max(len(df), 1)
    strata_candidates: List[str] = []

    for _, row in legacy_md.iterrows():
        name = row["column"]
        role_str = row["role"]
        series = df[name]

        total = n_rows
        missing = int(series.isna().sum())
        unique = int(series.nunique(dropna=True))
        uniqueness_ratio = float(unique / total) if total else 0.0

        stats = ColumnStats(
            missing=missing,
            total=total,
            unique=unique,
            uniqueness_ratio=uniqueness_ratio,
            dtype=str(series.dtype),
        )

        if role_str == "Direct Identifier":
            role = "direct_id"
            direct_ids.append(name)
        elif role_str == "Quasi-identifier":
            role = "quasi"
            quasi_ids.append(name)
        elif role_str == "Sensitive":
            role = "sensitive"
            sensitive.append(name)
        else:
            role = "non_sensitive"
            non_sensitive.append(name)

        reasons: List[str] = [f"legacy:{role_str}"]

        if uniqueness_ratio > 0.9:
            reasons.append("high_uniqueness")
        pii_types = _detect_pii_like(series)
        if pii_types:
            reasons.append("pii_patterns:" + ",".join(pii_types))
        if _is_date_like(name.lower(), series):
            reasons.append("date_like")

        if role in ("quasi", "non_sensitive") and any(
            kw in name.lower() for kw in ("district", "sector", "region", "province")
        ):
            strata_candidates.append(name)

        columns[name] = ColumnInfo(
            name=name,
            role=role,
            reasons=reasons,
            stats=stats,
        )

    seen = set()
    strata_candidates = [c for c in strata_candidates if not (c in seen or seen.add(c))]

    return DatasetMetadata(
        columns=columns,
        direct_identifiers=direct_ids,
        quasi_identifiers=quasi_ids,
        sensitive=sensitive,
        non_sensitive=non_sensitive,
        strata_candidates=strata_candidates,
    )
