"""
Synthetic Data API Routes
Uses APEDP (Adaptive Permutation-Enhanced Differential Privacy) for generation.
"""

from fastapi import APIRouter, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional, Dict, List
import pandas as pd
import numpy as np
import json
import traceback
import tempfile
import os

from .apedp.identify import identify_columns, prepare_dataframe, get_columns_by_role
from .apedp.synthesize import generate_synthetic_data, self_check
from .apedp.report import generate_report
from .apedp.codebook import apply_codebook

router = APIRouter(prefix="/synthetic", tags=["Synthetic Data"])

_sessions: Dict = {}


def set_sessions(sessions: Dict):
    global _sessions
    _sessions = sessions


def _safe_value(v):
    """Convert numpy/nan values to JSON-safe Python types."""
    if v is None:
        return None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def _safe_records(records: list) -> list:
    return [{k: _safe_value(v) for k, v in row.items()} for row in records]


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ session data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/session-data")
async def get_session_data(session_id: str):
    """Return original dataset info and preview."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    df: pd.DataFrame = _sessions[session_id]['df']
    try:
        sample = _safe_records(df.head(10).replace({np.nan: None}).to_dict('records'))
        return {
            "session_id": session_id,
            "shape": [int(df.shape[0]), int(df.shape[1])],
            "columns": df.columns.tolist(),
            "sample_data": sample,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting session data: {e}")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ identify â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/identify")
async def identify_dataset(session_id: str = Form(...)):
    """
    Classify each column as Direct Identifier / Quasi-identifier / Sensitive / Non-sensitive.

    Priority:
      1. Quasi-selection detection_result already in session (auto-detect was run).
      2. Explicit quasi_identifiers / sensitive_attributes saved by the quasi-selection step.
      3. Built-in heuristic pattern matching (no external dependency).
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    df: pd.DataFrame = session['df']

    try:
        # ── Option 1: full detection result from quasi-selection ──────────────
        # detection_result keys: direct_identifiers, quasi_identifiers,
        # sensitive_attributes, non_sensitive, details[{column_name, class, ...}]
        detection = session.get('detection_result')
        if detection and isinstance(detection, dict) and 'details' in detection:
            qs_map: dict = {}
            for item in detection['details']:
                col = (item.get('column_name') or item.get('column')
                       or item.get('name') or item.get('col'))
                cls = (item.get('class') or item.get('classification')
                       or item.get('role') or '').upper()
                if col:
                    qs_map[col] = cls

            rows = []
            for col in df.columns:
                cls = qs_map.get(col, 'NON_SENSITIVE')
                if 'DIRECT' in cls:
                    role, action = 'Direct Identifier', 'Drop'
                elif 'QUASI' in cls:
                    role, action = 'Quasi-identifier', 'Keep'
                elif 'SENSITIVE' in cls:
                    role, action = 'Sensitive', 'Keep'
                else:
                    role, action = 'Non-sensitive', 'Keep'
                rows.append({'column': col, 'dtype': str(df[col].dtype), 'role': role, 'action': action})
            metadata_df = pd.DataFrame(rows)
            source = 'quasi-selection detection'

        # ── Option 2: explicit / suggested lists from quasi-selection ─────────
        elif (session.get('quasi_identifiers') or session.get('sensitive_attributes')
              or session.get('suggested_quasi_identifiers')):
            qi_set   = set(session.get('quasi_identifiers')
                           or session.get('suggested_quasi_identifiers', []))
            sens_set = set(session.get('sensitive_attributes')
                           or session.get('suggested_sensitive_attributes', []))
            direct_set = set(session.get('direct_identifiers',
                             detection.get('direct_identifiers', []) if detection else []))

            rows = []
            for col in df.columns:
                if col in direct_set:
                    role, action = 'Direct Identifier', 'Drop'
                elif col in qi_set:
                    role, action = 'Quasi-identifier', 'Keep'
                elif col in sens_set:
                    role, action = 'Sensitive', 'Keep'
                else:
                    role, action = 'Non-sensitive', 'Keep'
                rows.append({'column': col, 'dtype': str(df[col].dtype), 'role': role, 'action': action})
            metadata_df = pd.DataFrame(rows)
            source = 'quasi-selection selection'

        # ── Option 3: built-in heuristic ──────────────────────────────────────
        else:
            metadata_df = identify_columns(df)
            source = 'heuristic'

        session['synthetic_metadata'] = metadata_df
        records = metadata_df.to_dict('records')
        role_counts = metadata_df['role'].value_counts().to_dict()
        return {
            "session_id": session_id,
            "source": source,
            "columns": records,
            "role_summary": role_counts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Identification error: {e}")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ generate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/generate-synthetic")
async def generate_synthetic_dataset(
    session_id: str = Form(...),
    epsilon: float = Form(1.0),
    n_samples: Optional[int] = Form(None),
    seed: int = Form(42),
    strata_keys: Optional[str] = Form(None),   # JSON array string
):
    """
    Generate synthetic data using APEDP (DP-marginals + stratified permutation).

    - epsilon: Privacy budget (lower = more private, less utility). Default 1.0.
    - n_samples: Number of output rows (defaults to original row count).
    - seed: Random seed for reproducibility.
    - strata_keys: JSON array of column names for stratified permutation.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    df: pd.DataFrame = session['df']

    if epsilon <= 0:
        raise HTTPException(status_code=400, detail="epsilon must be > 0")

    n_rows = int(n_samples) if n_samples and n_samples > 0 else len(df)

    # Parse strata keys
    parsed_strata: List[str] = []
    if strata_keys:
        try:
            parsed_strata = json.loads(strata_keys)
        except Exception:
            parsed_strata = [s.strip() for s in strata_keys.split(',') if s.strip()]
    # Filter to columns that actually exist
    parsed_strata = [k for k in parsed_strata if k in df.columns]

    try:
        # Run identification if not already done
        metadata_df: pd.DataFrame = (
            session['synthetic_metadata']
            if 'synthetic_metadata' in session
            else identify_columns(df)
        )
        session['synthetic_metadata'] = metadata_df

        # Drop direct identifiers
        df_clean, dropped_cols = prepare_dataframe(df, metadata_df)

        # Generate synthetic data
        synthetic_df = generate_synthetic_data(
            df=df_clean,
            metadata_df=metadata_df,
            epsilon=epsilon,
            strata_keys=parsed_strata,
            n_rows=n_rows,
            seed=seed,
        )

        # Validation self-check — convert any numpy.bool_ to Python bool
        checks = {k: bool(v) if isinstance(v, (bool, np.bool_)) else _safe_value(v)
                  for k, v in self_check(df_clean, synthetic_df, metadata_df, n_rows, epsilon).items()}

        # Store in session
        session['synthetic_df'] = synthetic_df

        # Sample for preview
        sample = _safe_records(synthetic_df.head(20).replace({np.nan: None}).to_dict('records'))

        return {
            "session_id": session_id,
            "original_shape": [int(df.shape[0]), int(df.shape[1])],
            "synthetic_shape": [int(synthetic_df.shape[0]), int(synthetic_df.shape[1])],
            "columns": synthetic_df.columns.tolist(),
            "dropped_columns": dropped_cols,
            "sample_data": sample,
            "epsilon": epsilon,
            "seed": seed,
            "strata_keys": parsed_strata,
            "self_check": checks,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synthetic generation error: {traceback.format_exc()}")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ report â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/report")
async def generate_quality_report(session_id: str = Form(...)):
    """
    Generate utility + privacy quality report for the most recently generated synthetic dataset.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _sessions[session_id]
    df: pd.DataFrame = session['df']
    synthetic_df: Optional[pd.DataFrame] = session.get('synthetic_df')
    if synthetic_df is None:
        raise HTTPException(status_code=400, detail="No synthetic data found. Run /generate-synthetic first.")

    metadata_df: pd.DataFrame = (
        session['synthetic_metadata']
        if 'synthetic_metadata' in session
        else identify_columns(df)
    )
    _, dropped_cols = prepare_dataframe(df, metadata_df)

    try:
        report = generate_report(
            original_df=df,
            synthetic_df=synthetic_df,
            metadata_df=metadata_df,
            epsilon=session.get('synthetic_epsilon', 1.0),
            seed=session.get('synthetic_seed', 42),
            strata_keys=session.get('synthetic_strata', []),
            dropped_columns=dropped_cols,
        )
        return JSONResponse(content=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation error: {e}")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ download â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/download-synthetic")
async def download_synthetic(session_id: str, format: str = "csv"):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    synth_df: Optional[pd.DataFrame] = _sessions[session_id].get('synthetic_df')
    if synth_df is None:
        raise HTTPException(status_code=400, detail="No synthetic data available. Run /generate-synthetic first.")
    try:
        if format == "csv":
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
            synth_df.to_csv(tmp.name, index=False)
            return FileResponse(tmp.name, filename=f"synthetic_{session_id}.csv", media_type="text/csv")
        elif format == "excel":
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            synth_df.to_excel(tmp.name, index=False)
            return FileResponse(
                tmp.name,
                filename=f"synthetic_{session_id}.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid format. Use 'csv' or 'excel'.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

