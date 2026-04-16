"""
Quasi Selection API Routes
Handles quasi-identifier and sensitive attribute selection.

Also exposes /auto-detect-columns which runs the HIES-based NLP pipeline
(ported from hies/src/) to automatically classify every column in the
uploaded dataset into one of:
  DIRECT_IDENTIFIER | QUASI_IDENTIFIER | SENSITIVE | NON_SENSITIVE
"""

from fastapi import APIRouter, HTTPException, Form
from typing import Optional, Dict, Any
import json

from .detector import (
    auto_detect_columns,
    validate_risk,
    generate_json_report,
    generate_csv_summary,
)

router = APIRouter(prefix="", tags=["Quasi Selection"])

# Global storage for sessions (will be injected from main.py)
_sessions = {}


def set_sessions(sessions: Dict):
    """Set the sessions dictionary from main.py"""
    global _sessions
    _sessions = sessions


@router.post("/select-quasi-identifiers")
async def select_quasi_identifiers(
    session_id: str = Form(...),
    quasi_identifiers: str = Form(...),  # JSON array
    sensitive_attributes: Optional[str] = Form(None)  # JSON array
):
    """
    Select quasi-identifiers and sensitive attributes
    """
    global _sessions
    
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        qi_list = json.loads(quasi_identifiers)
        sens_list = json.loads(sensitive_attributes) if sensitive_attributes else []
        
        # Validate columns exist
        df = _sessions[session_id]['df']
        missing_qis = [qi for qi in qi_list if qi not in df.columns]
        if missing_qis:
            raise HTTPException(status_code=400, detail=f"Columns not found: {missing_qis}")
        
        missing_sens = [sens for sens in sens_list if sens not in df.columns]
        if missing_sens:
            raise HTTPException(status_code=400, detail=f"Columns not found: {missing_sens}")
        
        # Update session
        _sessions[session_id]['quasi_identifiers'] = qi_list
        _sessions[session_id]['sensitive_attributes'] = sens_list
        
        return {
            "message": "Quasi-identifiers selected successfully",
            "quasi_identifiers": qi_list,
            "sensitive_attributes": sens_list
        }
    
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-detect-columns")
async def auto_detect_columns_endpoint(session_id: str = Form(...)):
    """
    Automatically detect column types using the HIES NLP pipeline.

    Analyses the uploaded CSV for the given session and classifies every
    column into one of:
      - DIRECT_IDENTIFIER  (e.g. name, email, phone, ID numbers)
      - QUASI_IDENTIFIER   (e.g. age, gender, occupation, location)
      - SENSITIVE          (e.g. income, religion, health)
      - NON_SENSITIVE      (everything else)

    Returns suggested quasi-identifiers and sensitive attributes so the
    frontend can pre-populate the selection UI, while still allowing the
    user to override.

    Response shape::

        {
          "direct_identifiers":   [...],
          "quasi_identifiers":    [...],
          "sensitive_attributes": [...],
          "non_sensitive":        [...],
          "details": [
            {
              "column_name": "...",
              "class": "QUASI_IDENTIFIER",
              "confidence": 0.85,
              "reasons": "...",
              "evidence": "..."
            },
            ...
          ]
        }
    """
    global _sessions

    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        df = _sessions[session_id]['df']
        result = auto_detect_columns(df)

        # Cache detection result so /generate-report and /generate-csv-summary can use it
        _sessions[session_id]['detection_result'] = result

        # Pre-populate the session with detected suggestions
        # (user can still override via /select-quasi-identifiers)
        _sessions[session_id].setdefault('suggested_quasi_identifiers',   result['quasi_identifiers'])
        _sessions[session_id].setdefault('suggested_sensitive_attributes', result['sensitive_attributes'])

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate-risk")
async def validate_risk_endpoint(
    session_id: str = Form(...),
    quasi_identifiers: Optional[str] = Form(None),  # JSON array; falls back to session value
):
    """
    Compute k-anonymity and re-identification risk for the selected QI columns.

    Response shape::

        {
          "risk_level":         "CRITICAL|HIGH|MEDIUM|LOW|UNDEFINED",
          "risk_description":   "...",
          "k_anonymity_metrics": { "k_anonymity": N, "unique_pct": P, ... },
          "riskiest_classes":   [...],
          "qi_columns":         [...]
        }
    """
    global _sessions

    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        df = _sessions[session_id]['df']

        if quasi_identifiers:
            qi_list = json.loads(quasi_identifiers)
        else:
            qi_list = _sessions[session_id].get('quasi_identifiers', [])

        if not qi_list:
            raise HTTPException(
                status_code=400,
                detail="No quasi-identifiers specified and none saved in session."
            )

        result = validate_risk(df, qi_list)
        return result

    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for quasi_identifiers")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-report")
async def generate_report_endpoint(session_id: str = Form(...)):
    """
    Generate a full JSON classification report for the current session.

    Requires that /auto-detect-columns has been called first (or that the
    session already holds a 'detection_result' key).
    """
    global _sessions

    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    detection = session.get('detection_result')
    if detection is None:
        raise HTTPException(
            status_code=400,
            detail="No detection results found. Run /auto-detect-columns first."
        )

    try:
        import pandas as pd
        details = detection.get('details', [])
        if not details:
            raise HTTPException(status_code=400, detail="Detection details are empty.")

        classification_df = pd.DataFrame(details)
        # Ensure required columns exist
        for col in ['column_name', 'class', 'confidence', 'reasons', 'evidence']:
            if col not in classification_df.columns:
                classification_df[col] = ''
        if 'normalized_name' not in classification_df.columns:
            classification_df['normalized_name'] = classification_df['column_name']

        report_json = generate_json_report(
            classification_df,
            dataset_name=session.get('filename', 'dataset'),
            total_rows=len(session['df']),
            total_cols=len(session['df'].columns),
        )
        return json.loads(report_json)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-csv-summary")
async def generate_csv_summary_endpoint(session_id: str = Form(...)):
    """
    Return a tabular CSV-style summary of column classifications.

    Response is a JSON array of row objects suitable for rendering in a
    table or downloading as CSV.
    """
    global _sessions

    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    detection = session.get('detection_result')
    if detection is None:
        raise HTTPException(
            status_code=400,
            detail="No detection results found. Run /auto-detect-columns first."
        )

    try:
        import pandas as pd
        details = detection.get('details', [])
        if not details:
            raise HTTPException(status_code=400, detail="Detection details are empty.")

        classification_df = pd.DataFrame(details)
        for col in ['column_name', 'class', 'confidence', 'reasons', 'evidence']:
            if col not in classification_df.columns:
                classification_df[col] = ''
        if 'normalized_name' not in classification_df.columns:
            classification_df['normalized_name'] = classification_df['column_name']

        summary_df = generate_csv_summary(classification_df)
        return summary_df.to_dict(orient='records')

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
