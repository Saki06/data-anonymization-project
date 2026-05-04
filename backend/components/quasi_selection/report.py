"""
Report generation utilities for the HIES column-classification pipeline.

Ported from hies/src/report.py
"""

import json
import pandas as pd
from datetime import datetime
from typing import Any, Dict, Optional


def generate_json_report(
    classification_df: pd.DataFrame,
    risk_results: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    dataset_name: Optional[str] = None,
    total_rows: Optional[int] = None,
    total_cols: Optional[int] = None,
) -> str:
    """
    Generate a JSON report of classifications and (optionally) risk assessment.

    Args:
        classification_df: DataFrame with classification results.
        risk_results:      Optional risk-validation results dict.
        metadata:          Optional metadata (e.g., filename, timestamp).
        dataset_name:      Optional dataset name for the metadata block.
        total_rows:        Optional total number of rows in the dataset.
        total_cols:        Optional total number of columns in the dataset.

    Returns:
        Indented JSON string.
    """
    meta = dict(metadata or {})
    if dataset_name is not None:
        meta['dataset_name'] = dataset_name
    if total_rows is not None:
        meta['total_rows'] = total_rows
    if total_cols is not None:
        meta['total_cols'] = total_cols

    report: Dict[str, Any] = {
        'metadata':        meta,
        'timestamp':       datetime.now().isoformat(),
        'classifications': classification_df.to_dict('records'),
        'summary': {
            'total_columns':      len(classification_df),
            'direct_identifiers': len(classification_df[classification_df['class'] == 'DIRECT_IDENTIFIER']),
            'quasi_identifiers':  len(classification_df[classification_df['class'] == 'QUASI_IDENTIFIER']),
            'sensitive':          len(classification_df[classification_df['class'] == 'SENSITIVE']),
            'non_sensitive':      len(classification_df[classification_df['class'] == 'NON_SENSITIVE']),
        },
    }

    if risk_results:
        report['risk_assessment'] = {
            'risk_level':       risk_results.get('risk_level'),
            'risk_description': risk_results.get('risk_description'),
            'k_anonymity':      risk_results.get('k_anonymity_metrics', {}).get('k_anonymity'),
            'unique_pct':       risk_results.get('k_anonymity_metrics', {}).get('unique_pct'),
            'qi_columns':       risk_results.get('qi_columns', []),
        }

    return json.dumps(report, indent=2, default=str)


def generate_csv_summary(classification_df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a CSV-friendly summary DataFrame of classification results.

    Columns: column_name, normalized_name, class, confidence, reasons, evidence.
    Confidence values are rounded to 2 decimal places.
    """
    summary = classification_df[[
        'column_name',
        'normalized_name',
        'class',
        'confidence',
        'reasons',
        'evidence',
    ]].copy()
    summary['confidence'] = summary['confidence'].round(2)
    return summary


def save_report_json(report_json: str, filepath: str) -> None:
    """
    Write a JSON report string to *filepath*.

    Args:
        report_json: JSON string produced by generate_json_report().
        filepath:    Output file path.
    """
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(report_json)


def save_report_csv(summary_df: pd.DataFrame, filepath: str) -> None:
    """
    Write a summary DataFrame to *filepath* as CSV.

    Args:
        summary_df: DataFrame produced by generate_csv_summary().
        filepath:   Output file path.
    """
    summary_df.to_csv(filepath, index=False, encoding='utf-8')
