"""
Enhanced Data Identification (Component 01).

Builds on the existing `apedp.identify.identify_columns` heuristics and
adds data-driven risk signals such as:
- uniqueness ratio / cardinality
- common PII patterns (email, phone, NIC-like IDs)
- date-of-birth-like and temporal patterns

Also supports manual overrides from the UI while keeping metadata
round-trippable via JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
import re

import numpy as np
import pandas as pd


EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[- ]?)?(?:\d{9,12})\b")
# Simple Sri Lanka NIC-like: 9 digits + letter or 12 digits
NIC_REGEX = re.compile(r"\b(?:\d{9}[vVxX]|\d{12})\b")
DATE_LIKE_COLNAME = re.compile(r"(dob|date[_ ]?of[_ ]?birth|birth[_ ]?date)", re.IGNORECASE)


@dataclass
class EnhancedColumnMetadata:
    """Rich metadata for a single column."""

    column: str
    dtype: str
    role: str  # direct / quasi / sensitive / non-sensitive
    action: str  # "Drop" or "Keep"

    # Data-driven signals
    uniqueness_ratio: float
    cardinality: int
    is_pii_like: bool
    pii_types: List[str]
    is_date_like: bool

    # User-editable fields
    manual_role: Optional[str] = None
    manual_action: Optional[str] = None

    def effective_role(self) -> str:
        """Return the role after applying any manual override."""
        return self.manual_role or self.role

    def effective_action(self) -> str:
        """Return the action after applying any manual override."""
        return self.manual_action or self.action

    def to_dict(self) -> Dict:
        """Convert to a plain dict for JSON / Pandas."""
        d = asdict(self)
        d["effective_role"] = self.effective_role()
        d["effective_action"] = self.effective_action()
        return d


def _detect_pii(series: pd.Series) -> Tuple[bool, List[str]]:
    """Detect simple PII patterns in a Series using regex-based heuristics."""
    pii_flags: List[str] = []
    if series.dtype == "O" or pd.api.types.is_string_dtype(series):
        sample = series.dropna().astype(str).head(500)
        text = " ".join(sample.tolist())
        if EMAIL_REGEX.search(text):
            pii_flags.append("email")
        if PHONE_REGEX.search(text):
            pii_flags.append("phone")
        if NIC_REGEX.search(text):
            pii_flags.append("nic")
    return (len(pii_flags) > 0, pii_flags)


def _is_date_like(col_name: str, series: pd.Series) -> bool:
    """Detect date-of-birth-like / temporal columns."""
    if DATE_LIKE_COLNAME.search(col_name):
        return True
    sample = series.dropna().head(200)
    if sample.empty:
        return False
    try:
        parsed = pd.to_datetime(sample, errors="coerce", infer_datetime_format=True)
        parsed_ratio = parsed.notna().mean()
        return bool(parsed_ratio > 0.7)
    except Exception:
        return False


def _legacy_identify_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Local legacy-like identification (name/data heuristics).
    Returns DataFrame with columns: ['column', 'role', 'action'].
    role values:
      - 'Direct Identifier'
      - 'Quasi-identifier'
      - 'Sensitive'
      - 'Non-sensitive'
    """
    rows: List[Dict] = []
    n = max(len(df), 1)

    for col in df.columns:
        s = df[col]
        col_lower = col.lower()
        role = "Non-sensitive"
        action = "Keep"

        is_pii_like, pii_types = _detect_pii(s)
        if is_pii_like:
            role = "Direct Identifier"
            action = "Drop"

        elif _is_date_like(col_lower, s):
            role = "Quasi-identifier"
            action = "Keep"

        else:
            uniq_ratio = float(s.nunique(dropna=True) / n) if n else 0.0
            if uniq_ratio > 0.98:
                role = "Quasi-identifier"
                action = "Keep"

            if any(k in col_lower for k in ("income", "salary", "wage", "disease", "religion", "ethnic", "politic")):
                role = "Sensitive"
                action = "Keep"

        rows.append({"column": col, "role": role, "action": action})

    return pd.DataFrame(rows)


def identify_with_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run legacy name-based identification and augment with data-driven signals.

    Args:
        df: Input DataFrame.

    Returns:
        Pandas DataFrame with one row per column and extended metadata fields.
    """
    base_md = _legacy_identify_columns(df)
    records: List[Dict] = []

    n_rows = max(len(df), 1)

    for _, row in base_md.iterrows():
        col = row["column"]
        series = df[col]
        col_lower = col.lower()

        uniqueness_ratio = float(series.nunique(dropna=True) / n_rows)
        cardinality = int(series.nunique(dropna=True))

        is_pii_like, pii_types = _detect_pii(series)
        is_date = _is_date_like(col_lower, series)

        meta = EnhancedColumnMetadata(
            column=col,
            dtype=str(series.dtype),
            role=row["role"],
            action=row["action"],
            uniqueness_ratio=uniqueness_ratio,
            cardinality=cardinality,
            is_pii_like=is_pii_like,
            pii_types=pii_types,
            is_date_like=is_date,
        )
        records.append(meta.to_dict())

    return pd.DataFrame(records)


def apply_manual_overrides(
    metadata_df: pd.DataFrame,
    overrides: Dict[str, Dict[str, str]],
) -> pd.DataFrame:
    """
    Apply manual overrides provided from the UI to metadata.

    Args:
        metadata_df: Output of `identify_with_signals`.
        overrides: Mapping column -> {"manual_role": ..., "manual_action": ...}

    Returns:
        Updated metadata DataFrame with manual_* fields populated.
    """
    md = metadata_df.copy()
    if "manual_role" not in md.columns:
        md["manual_role"] = None
    if "manual_action" not in md.columns:
        md["manual_action"] = None

    for col, ov in overrides.items():
        if col not in md["column"].values:
            continue
        mask = md["column"] == col
        if "manual_role" in ov:
            md.loc[mask, "manual_role"] = ov["manual_role"]
        if "manual_action" in ov:
            md.loc[mask, "manual_action"] = ov["manual_action"]

    eff_roles = []
    eff_actions = []
    for _, row in md.iterrows():
        role = row.get("manual_role") or row["role"]
        action = row.get("manual_action") or row["action"]
        eff_roles.append(role)
        eff_actions.append(action)
    md["effective_role"] = eff_roles
    md["effective_action"] = eff_actions

    return md
