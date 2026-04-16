"""
Metadata structures for Component 01 (Data Identification).

Defines the normalized metadata object exposed to the rest of the
pipeline and persisted to JSON in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Any

import pandas as pd


@dataclass
class ColumnStats:
    """Basic statistics for a single column."""

    missing: int
    total: int
    unique: int
    uniqueness_ratio: float
    dtype: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ColumnInfo:
    """Role, reasons, and stats for a column."""

    name: str
    role: str  # "direct_id" | "quasi" | "sensitive" | "non_sensitive"
    reasons: List[str]
    stats: ColumnStats

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "role": self.role,
            "reasons": self.reasons,
            "stats": self.stats.to_dict(),
        }
        return d


@dataclass
class DatasetMetadata:
    """
    Top-level metadata object used across components.

    Attributes:
        columns: mapping from name -> ColumnInfo
        direct_identifiers, quasi_identifiers, sensitive, non_sensitive: lists of column names
        strata_candidates: suggested strata keys (e.g., district/sector)
    """

    columns: Dict[str, ColumnInfo]
    direct_identifiers: List[str]
    quasi_identifiers: List[str]
    sensitive: List[str]
    non_sensitive: List[str]
    strata_candidates: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "columns": {name: col.to_dict() for name, col in self.columns.items()},
            "direct_identifiers": self.direct_identifiers,
            "quasi_identifiers": self.quasi_identifiers,
            "sensitive": self.sensitive,
            "non_sensitive": self.non_sensitive,
            "strata_candidates": self.strata_candidates,
        }

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "DatasetMetadata":
        """
        Convenience constructor for tests; most callers should use the
        builder in `pii_detection.build_metadata`.
        """
        cols: Dict[str, ColumnInfo] = {}
        direct: List[str] = []
        quasi: List[str] = []
        sensitive: List[str] = []
        non_sensitive: List[str] = []

        for col in df.columns:
            total = len(df)
            missing = int(df[col].isna().sum())
            unique = int(df[col].nunique(dropna=True))
            uniqueness_ratio = float(unique / total) if total else 0.0
            stats = ColumnStats(
                missing=missing,
                total=total,
                unique=unique,
                uniqueness_ratio=uniqueness_ratio,
                dtype=str(df[col].dtype),
            )
            info = ColumnInfo(
                name=col,
                role="non_sensitive",
                reasons=[],
                stats=stats,
            )
            cols[col] = info
            non_sensitive.append(col)

        return cls(
            columns=cols,
            direct_identifiers=direct,
            quasi_identifiers=quasi,
            sensitive=sensitive,
            non_sensitive=non_sensitive,
            strata_candidates=[],
        )
