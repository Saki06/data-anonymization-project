"""
Component 01: Data Identification

Enhanced identification module that combines:
- name-based heuristics (backwards compatible with apedp.identify)
- data-driven signals (uniqueness, cardinality, PII patterns)

Key entry points:
- `build_metadata(df)` -> `DatasetMetadata`
- `identify_with_signals(df)` -> pandas DataFrame (richer table for UI)
"""

from .metadata import ColumnStats, ColumnInfo, DatasetMetadata
from .pii_detection import build_metadata
from .identify import EnhancedColumnMetadata, identify_with_signals, apply_manual_overrides

__all__ = [
    "ColumnStats",
    "ColumnInfo",
    "DatasetMetadata",
    "build_metadata",
    "EnhancedColumnMetadata",
    "identify_with_signals",
    "apply_manual_overrides",
]
