"""
Data Identification Module (Component 01).

Classifies each column in a DataFrame into:
  Direct Identifier | Quasi-identifier | Sensitive | Non-sensitive

This module is self-contained (no sub-package dependency) so it can
always be imported safely.
"""

from typing import List, Tuple
import re
import pandas as pd

# ── heuristic patterns ────────────────────────────────────────────────────────

_DIRECT_PATTERNS = re.compile(
    r'\b(name|surname|forename|nic|passport|id_no|id_number|national_id|'
    r'email|e_mail|phone|mobile|telephone|fax|address|street|house_no|'
    r'dob|date_of_birth|birth_date|birthdate|ssn|tax_id|driving_licen)\b',
    re.I,
)
_QUASI_PATTERNS = re.compile(
    r'\b(age|gender|sex|race|ethnicity|religion|marital|district|province|'
    r'region|division|zone|ward|nationality|education|occupation|salary|'
    r'income|employment|household|family)\b',
    re.I,
)
_SENSITIVE_PATTERNS = re.compile(
    r'\b(health|disease|diagnosis|hiv|aids|drug|mental|disability|crime|'
    r'conviction|finance|debt|credit|score|bank|political|vote)\b',
    re.I,
)


def _infer_role(col_name: str, series: pd.Series) -> str:
    cn = col_name.lower()
    if _DIRECT_PATTERNS.search(cn):
        return "Direct Identifier"
    if _SENSITIVE_PATTERNS.search(cn):
        return "Sensitive"
    if _QUASI_PATTERNS.search(cn):
        return "Quasi-identifier"
    # High-cardinality string columns are likely identifiers
    if series.dtype == object and series.nunique() / max(len(series), 1) > 0.9:
        return "Direct Identifier"
    return "Non-sensitive"


def identify_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a tabular view of column roles for each column."""
    rows = []
    for col in df.columns:
        role = _infer_role(col, df[col])
        rows.append({
            "column": col,
            "dtype": str(df[col].dtype),
            "role": role,
            "action": "Drop" if role == "Direct Identifier" else "Keep",
        })
    return pd.DataFrame(rows)


def get_columns_by_role(metadata_df: pd.DataFrame, role: str) -> List[str]:
    """Get column names by role from the legacy DataFrame representation."""
    return metadata_df[metadata_df["role"] == role]["column"].tolist()


def prepare_dataframe(df: pd.DataFrame, metadata_df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Prepare dataframe by dropping direct identifiers."""
    dropped_cols = get_columns_by_role(metadata_df, "Direct Identifier")
    df_clean = df.drop(columns=dropped_cols, errors="ignore")
    return df_clean, dropped_cols


from typing import List, Tuple
import re
import pandas as pd

_DIRECT_ID_KEYWORDS = re.compile(
    r'\b(id|name|email|phone|mobile|nic|passport|address|ssn|national_id|surname|firstname|lastname)\b',
    re.IGNORECASE,
)
_QUASI_KEYWORDS = re.compile(
    r'\b(age|gender|sex|race|ethnicity|religion|district|region|province|zip|postal|dob|birth|year|marital|education|occupation|salary|income)\b',
    re.IGNORECASE,
)
_SENSITIVE_KEYWORDS = re.compile(
    r'\b(disease|diagnosis|condition|hiv|cancer|drug|alcohol|mental|salary|income|crime|offense|conviction)\b',
    re.IGNORECASE,
)


def identify_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Heuristic column classification.
    Returns a DataFrame with columns: column, dtype, role, action.
    """
    rows = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        uniqueness = df[col].nunique() / max(len(df), 1)

        if _DIRECT_ID_KEYWORDS.search(col) or uniqueness > 0.9:
            role = 'Direct Identifier'
            action = 'Drop'
        elif _SENSITIVE_KEYWORDS.search(col):
            role = 'Sensitive'
            action = 'Keep'
        elif _QUASI_KEYWORDS.search(col):
            role = 'Quasi-identifier'
            action = 'Keep'
        else:
            role = 'Non-sensitive'
            action = 'Keep'

        rows.append({'column': col, 'dtype': dtype, 'role': role, 'action': action})

    return pd.DataFrame(rows)


def get_columns_by_role(metadata_df: pd.DataFrame, role: str) -> List[str]:
    return metadata_df[metadata_df['role'] == role]['column'].tolist()


def prepare_dataframe(df: pd.DataFrame, metadata_df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    dropped_cols = get_columns_by_role(metadata_df, 'Direct Identifier')
    df_clean = df.drop(columns=dropped_cols, errors='ignore')
    return df_clean, dropped_cols
