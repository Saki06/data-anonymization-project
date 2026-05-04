"""
Column Classification Detector — orchestrator module.

Imports from the individual sub-modules and exposes ``auto_detect_columns``
as the single public entry-point for the quasi-selection API routes.

Sub-modules:
  config.py            : keyword / regex / threshold constants
  preprocess.py        : column normalisation & profiling
  detect_direct.py     : direct-identifier detection
  detect_qi_sensitive.py: quasi-identifier & sensitive-attribute detection
  report.py            : JSON / CSV report generation
  risk_validation.py   : k-anonymity & re-identification risk assessment
"""

import numpy as np
import pandas as pd
from typing import Any, Dict, List

# Re-export everything so routes.py only needs to import from here
from .config import (                           # noqa: F401
    HIGH_PRIORITY_DIRECT_IDENTIFIERS,
    DIRECT_IDENTIFIER_KEYWORDS,
    DIRECT_IDENTIFIER_PATTERNS,
    HIGH_PRIORITY_QUASI_IDENTIFIERS,
    QUASI_IDENTIFIER_KEYWORDS,
    HIGH_PRIORITY_SENSITIVE,
    SENSITIVE_KEYWORDS,
    COLUMN_NORMALIZE_PATTERNS,
    CONFIDENCE_THRESHOLDS,
    RISK_THRESHOLDS,
)
from .preprocess import (                       # noqa: F401
    normalize_column_name,
    infer_dtype,
    compute_profiling_stats,
    preprocess_dataframe,
    preprocess_csv,
    get_column_summary,
)
from .detect_direct import detect_direct_identifiers  # noqa: F401
from .detect_qi_sensitive import (              # noqa: F401
    detect_qi_and_sensitive,
    combine_classifications,
)
from .report import (                           # noqa: F401
    generate_json_report,
    generate_csv_summary,
    save_report_json,
    save_report_csv,
)
from .risk_validation import (                  # noqa: F401
    compute_equivalence_classes,
    compute_k_anonymity,
    get_riskiest_classes,
    get_risky_groups,
    get_risk_level,
    search_qi_combinations,
    compute_l_diversity,
    get_detailed_evidence,
    validate_risk,
)


# ---------------------------------------------------------------------------
# High-level pipeline
# ---------------------------------------------------------------------------

def auto_detect_columns(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Run the full HIES detection pipeline on *df* and return a structured dict
    suitable for a JSON API response.

    Returns::

        {
            "direct_identifiers":   [column_name, ...],
            "quasi_identifiers":    [column_name, ...],
            "sensitive_attributes": [column_name, ...],
            "non_sensitive":        [column_name, ...],
            "details": [
                {
                    "column_name": ...,
                    "class": ...,
                    "confidence": ...,
                    "reasons": ...,
                    "evidence": ...
                },
                ...
            ]
        }
    """
    df_norm, profiling_df = preprocess_dataframe(df)

    direct_df      = detect_direct_identifiers(df_norm, profiling_df)
    direct_cols    = direct_df['normalized_name'].tolist() if not direct_df.empty else []

    qi_sens_df     = detect_qi_and_sensitive(df_norm, profiling_df, direct_cols)
    combined_df    = combine_classifications(direct_df, qi_sens_df)

    # Build categorised lists (use original column names)
    direct_ids  = combined_df[combined_df['class'] == 'DIRECT_IDENTIFIER']['column_name'].tolist()
    qis         = combined_df[combined_df['class'] == 'QUASI_IDENTIFIER']['column_name'].tolist()
    sensitives  = combined_df[combined_df['class'] == 'SENSITIVE']['column_name'].tolist()
    non_sens    = combined_df[combined_df['class'] == 'NON_SENSITIVE']['column_name'].tolist()

    details = combined_df.to_dict(orient='records')
    # convert numpy types to native python for JSON serialisation
    for row in details:
        for k, v in row.items():
            if isinstance(v, (np.integer,)):
                row[k] = int(v)
            elif isinstance(v, (np.floating,)):
                row[k] = float(v)

    return {
        "direct_identifiers":   direct_ids,
        "quasi_identifiers":    qis,
        "sensitive_attributes": sensitives,
        "non_sensitive":        non_sens,
        "details":              details,
    }
