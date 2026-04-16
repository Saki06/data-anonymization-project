from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse


BASE_DIR = Path(__file__).parent
router = APIRouter(prefix="", tags=["Re-identification"])


# -----------------------------------------------------------------------------
# Optional agent imports (graceful degradation)
# -----------------------------------------------------------------------------
try:
    from .agents.agent1_data_inspector.inspector import DataInspector

    _HAS_AGENT1 = True
except Exception as _e1:
    _HAS_AGENT1 = False
    print(f"[WARN] Agent1 (DataInspector) not available: {_e1}")

try:
    from .agents.agent2_identifier_manager.identifier_manager import IdentifierManager

    _HAS_AGENT2 = True
except Exception as _e2:
    _HAS_AGENT2 = False
    print(f"[WARN] Agent2 (IdentifierManager) not available: {_e2}")

try:
    from .agents.agent3_pair_generator.pair_generator import PairGenerator

    _HAS_AGENT3 = True
except Exception as _e3:
    _HAS_AGENT3 = False
    print(f"[WARN] Agent3 (PairGenerator) not available: {_e3}")

try:
    from .agents.agent4_ml_attacker.agent4_ml_attacker import MLAttackModel

    _HAS_AGENT4 = True
except Exception as _e4:
    _HAS_AGENT4 = False
    print(f"[WARN] Agent4 (MLAttackModel) not available: {_e4}")

try:
    from .agents.agent5_risk_scorer.risk_scorer import RiskScorer

    _HAS_AGENT5 = True
except Exception as _e5:
    _HAS_AGENT5 = False
    print(f"[WARN] Agent5 (RiskScorer) not available: {_e5}")

try:
    from .agents.agent5_risk_scorer.shap_explainer import AttackModelExplainer

    _HAS_SHAP = True
except Exception as _esh:
    _HAS_SHAP = False
    print(f"[WARN] AttackModelExplainer (SHAP) not available: {_esh}")

try:
    from .agents.agent5_risk_scorer.internal_risk import InternalRiskAnalyzer

    _HAS_INTERNAL = True
except Exception as _ei:
    _HAS_INTERNAL = False
    print(f"[WARN] InternalRiskAnalyzer not available: {_ei}")

try:
    from .agents.agent6_risk_aggregator.risk_aggregator import RiskAggregator

    _HAS_AGENT6 = True
except Exception as _e6:
    _HAS_AGENT6 = False
    print(f"[WARN] Agent6 (RiskAggregator) not available: {_e6}")

try:
    from .agents.agent7_llm_explainer.llm_explainer import LLMExplainer

    _HAS_AGENT7 = True
except Exception as _e7:
    _HAS_AGENT7 = False
    print(f"[WARN] Agent7 (LLMExplainer) not available: {_e7}")


# -----------------------------------------------------------------------------
# Session wiring
# -----------------------------------------------------------------------------
_sessions: Dict[str, Dict[str, Any]] = {}


def set_sessions(sessions: Dict[str, Dict[str, Any]]) -> None:
    global _sessions
    _sessions = sessions


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _safe_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_json(i) for i in obj]
    if isinstance(obj, tuple):
        return [_safe_json(i) for i in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        value = float(obj)
        if np.isnan(value) or np.isinf(value):
            return None
        return value
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.DataFrame):
        return _safe_json(obj.to_dict("records"))
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj


def _session_to_csv(df: pd.DataFrame, name: str) -> Path:
    out = BASE_DIR / "data" / "raw" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out


def _resolve_pair_dataset_path(pairs_dir: Path) -> Path:
    pair_dataset = pairs_dir / "pair_dataset.csv"
    if pair_dataset.exists():
        return pair_dataset

    all_pairs = pairs_dir / "all_pairs.csv"
    if all_pairs.exists():
        return all_pairs

    train_path = pairs_dir / "train_pairs.csv"
    test_path = pairs_dir / "test_pairs.csv"
    if train_path.exists() and test_path.exists():
        train_df = pd.read_csv(train_path)
        test_df = pd.read_csv(test_path)
        merged = pd.concat([train_df, test_df], ignore_index=True)
        merged.to_csv(pair_dataset, index=False)
        return pair_dataset

    return pair_dataset


def _resolve_shap_global_path(shap_dir: Path) -> Optional[Path]:
    candidates = [
        shap_dir / "shap_global_feature_importance.csv",
        shap_dir / "shap_global_summary.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _normalize_inspection_output(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize Agent1 output to the frontend contract used by page.tsx."""
    normalized = dict(result or {})

    schema_validation = normalized.get("schema_validation") or {}
    data_profile = normalized.get("data_profile") or {}
    overview = data_profile.get("dataset_overview") or {}
    column_profiles = data_profile.get("column_profiles") or {}

    total_rows = int(
        overview.get("total_rows")
        if overview.get("total_rows") is not None
        else overview.get("rows")
        if overview.get("rows") is not None
        else schema_validation.get("total_rows", 0)
    )
    total_columns = int(
        overview.get("total_columns")
        if overview.get("total_columns") is not None
        else overview.get("columns")
        if overview.get("columns") is not None
        else schema_validation.get("total_columns", 0)
    )
    total_cells = int(max(total_rows * total_columns, 0))

    duplicate_rows = int(overview.get("duplicate_rows", 0))
    duplicate_percentage = (
        float(overview.get("duplicate_percentage"))
        if overview.get("duplicate_percentage") is not None
        else float(overview.get("duplicate_row_pct", 0.0))
    )

    data_profile["dataset_overview"] = {
        "total_rows": total_rows,
        "total_columns": total_columns,
        "total_cells": int(overview.get("total_cells", total_cells)),
        "memory_usage_mb": float(overview.get("memory_usage_mb", 0.0)),
        "duplicate_rows": duplicate_rows,
        "duplicate_percentage": duplicate_percentage,
    }

    missing_report = normalized.get("missing_value_report") or {}
    if "missing_summary" in missing_report and "column_analysis" in missing_report:
        missing_summary = missing_report.get("missing_summary") or {}
        column_analysis = missing_report.get("column_analysis") or {}
    else:
        by_column = missing_report.get("by_column") or {}
        column_analysis = {}
        for col, info in by_column.items():
            missing_count = int(info.get("missing_count", 0))
            missing_pct = float(info.get("missing_pct", 0.0))
            dtype = str((column_profiles.get(col) or {}).get("dtype", "unknown"))
            column_analysis[col] = {
                "missing_count": missing_count,
                "missing_rate": missing_pct / 100.0,
                "dtype": dtype,
            }

        total_missing = int(missing_report.get("total_missing", 0))
        missing_summary = {
            "total_missing": total_missing,
            "total_cells": total_cells,
            "overall_missing_rate": float(total_missing / total_cells) if total_cells > 0 else 0.0,
            "columns_with_missing": int(sum(1 for _, info in column_analysis.items() if info.get("missing_count", 0) > 0)),
        }

    normalized["missing_value_report"] = {
        "missing_summary": {
            "total_missing": int(missing_summary.get("total_missing", 0)),
            "total_cells": int(missing_summary.get("total_cells", total_cells)),
            "overall_missing_rate": float(missing_summary.get("overall_missing_rate", 0.0)),
            "columns_with_missing": int(missing_summary.get("columns_with_missing", 0)),
        },
        "column_analysis": column_analysis,
    }

    dq = data_profile.get("data_quality") or {}
    completeness_pct = (
        float(dq.get("completeness_percentage"))
        if dq.get("completeness_percentage") is not None
        else float(dq.get("completeness_pct", 0.0))
    )
    total_null_cells = (
        int(dq.get("total_null_cells"))
        if dq.get("total_null_cells") is not None
        else int(dq.get("missing_cells", normalized["missing_value_report"]["missing_summary"]["total_missing"]))
    )
    data_profile["data_quality"] = {
        "completeness_percentage": completeness_pct,
        "total_null_cells": total_null_cells,
        "total_null_percentage": float((total_null_cells / total_cells) * 100.0) if total_cells > 0 else 0.0,
        "columns_with_nulls": int(len(dq.get("columns_with_missing", []))) if isinstance(dq.get("columns_with_missing"), list) else int(dq.get("columns_with_nulls", 0)),
        "columns_fully_null": int(len(dq.get("fully_empty_columns", []))) if isinstance(dq.get("fully_empty_columns"), list) else int(dq.get("columns_fully_null", 0)),
    }

    stats = data_profile.get("statistical_summary") or {}
    if all(k in stats for k in ["numeric_columns_count", "categorical_columns_count", "datetime_columns_count"]):
        stat_counts = {
            "numeric_columns_count": int(stats.get("numeric_columns_count", 0)),
            "categorical_columns_count": int(stats.get("categorical_columns_count", 0)),
            "datetime_columns_count": int(stats.get("datetime_columns_count", 0)),
        }
    else:
        numeric_count = 0
        categorical_count = 0
        datetime_count = 0
        for _, profile in column_profiles.items():
            dtype_group = str(profile.get("dtype_group", "")).lower()
            dtype_name = str(profile.get("dtype", "")).lower()
            if dtype_group == "numeric" or any(x in dtype_name for x in ["int", "float", "double", "number"]):
                numeric_count += 1
            elif dtype_group == "datetime" or "datetime" in dtype_name:
                datetime_count += 1
            else:
                categorical_count += 1
        stat_counts = {
            "numeric_columns_count": numeric_count,
            "categorical_columns_count": categorical_count,
            "datetime_columns_count": datetime_count,
        }
    data_profile["statistical_summary"] = stat_counts
    normalized["data_profile"] = data_profile

    anomaly_report = normalized.get("anomaly_report") or {}
    anomalies: List[Dict[str, Any]]
    if "anomalies" in anomaly_report and isinstance(anomaly_report.get("anomalies"), list):
        anomalies = anomaly_report.get("anomalies") or []
    else:
        anomalies = []
        numeric_outliers = anomaly_report.get("numeric_outliers") or {}
        for col, info in numeric_outliers.items():
            anomalies.append(
                {
                    "column": col,
                    "type": "statistical_outlier",
                    "count": int(info.get("outlier_count", 0)),
                    "percentage": float(info.get("outlier_pct", 0.0)),
                }
            )
        categorical_alerts = anomaly_report.get("categorical_alerts") or {}
        for col, info in categorical_alerts.items():
            anomalies.append(
                {
                    "column": col,
                    "type": "high_cardinality",
                    "unique_count": int(len((info.get("top_values") or {}).keys())),
                    "unique_ratio": float(info.get("unique_ratio", 0.0)),
                    "note": "Derived from categorical alerts",
                }
            )

    normalized["anomaly_report"] = {
        "anomalies": anomalies,
        "total_anomalies": int(len(anomalies)),
    }

    merged_shape = normalized.get("merged_dataset_shape")
    if isinstance(merged_shape, tuple):
        normalized["merged_dataset_shape"] = [int(merged_shape[0]), int(merged_shape[1])]

    return normalized


def _basic_inspection_fallback(df: pd.DataFrame) -> Dict[str, Any]:
    total_rows = int(len(df))
    total_columns = int(len(df.columns))
    total_cells = int(total_rows * total_columns)

    duplicate_columns = df.columns[df.columns.duplicated()].tolist()
    empty_columns = [col for col in df.columns if df[col].isna().all()]
    constant_columns = [
        col for col in df.columns if df[col].dropna().nunique() <= 1 and not df[col].dropna().empty
    ]

    null_rates = df.isna().mean()
    high_null_columns = [
        {"column": col, "null_rate": round(float(rate), 3)}
        for col, rate in null_rates.items()
        if float(rate) >= 0.5
    ]

    column_analysis: Dict[str, Dict[str, Any]] = {}
    column_profiles: Dict[str, Dict[str, Any]] = {}
    for col in df.columns:
        missing_count = int(df[col].isna().sum())
        unique_count = int(df[col].nunique(dropna=True))
        column_analysis[col] = {
            "missing_count": missing_count,
            "missing_rate": float(missing_count / total_rows) if total_rows > 0 else 0.0,
            "dtype": str(df[col].dtype),
        }
        column_profiles[col] = {
            "data_type": str(df[col].dtype),
            "null_percentage": round(float(column_analysis[col]["missing_rate"] * 100), 2),
            "unique_count": unique_count,
            "unique_percentage": round(float((unique_count / total_rows) * 100), 2) if total_rows > 0 else 0.0,
        }

    numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
    categorical_cols = list(df.select_dtypes(include=["object", "category", "string"]).columns)
    datetime_cols = list(df.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns)

    anomalies: List[Dict[str, Any]] = []
    for col in numeric_cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 8:
            continue
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = int(((series < lower) | (series > upper)).sum())
        if outliers > 0:
            anomalies.append(
                {
                    "column": col,
                    "type": "statistical_outlier",
                    "count": outliers,
                    "percentage": round(float(outliers / max(len(series), 1) * 100), 2),
                }
            )

    for col in categorical_cols:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        unique_ratio = float(non_null.nunique() / len(non_null))
        if unique_ratio > 0.95 and len(non_null) >= 30:
            anomalies.append(
                {
                    "column": col,
                    "type": "high_cardinality",
                    "unique_count": int(non_null.nunique()),
                    "unique_ratio": round(unique_ratio, 3),
                }
            )

    issues_found = len(duplicate_columns) + len(empty_columns) + len(constant_columns) + len(high_null_columns)

    return {
        "fallback_mode": True,
        "fallback_reason": "Agent1 import failed; generated basic inspection in routes.py",
        "merge_report": {"files_processed": 1, "fallback": True},
        "schema_validation": {
            "total_columns": total_columns,
            "total_rows": total_rows,
            "validation_passed": issues_found == 0,
            "issues_found": int(issues_found),
            "duplicate_columns": duplicate_columns,
            "empty_columns": empty_columns,
            "constant_columns": constant_columns,
            "high_null_columns": high_null_columns,
        },
        "missing_value_report": {
            "missing_summary": {
                "total_missing": int(df.isna().sum().sum()),
                "total_cells": total_cells,
                "overall_missing_rate": float(df.isna().sum().sum() / total_cells) if total_cells > 0 else 0.0,
                "columns_with_missing": int((df.isna().sum() > 0).sum()),
            },
            "column_analysis": column_analysis,
        },
        "data_profile": {
            "dataset_overview": {
                "total_rows": total_rows,
                "total_columns": total_columns,
                "total_cells": total_cells,
                "memory_usage_mb": round(float(df.memory_usage(deep=True).sum() / (1024 * 1024)), 3),
                "duplicate_rows": int(df.duplicated().sum()),
                "duplicate_percentage": round(float(df.duplicated().mean() * 100), 2) if total_rows > 0 else 0.0,
            },
            "data_quality": {
                "completeness_percentage": round(float((1 - (df.isna().sum().sum() / total_cells)) * 100), 2) if total_cells > 0 else 100.0,
                "total_null_cells": int(df.isna().sum().sum()),
                "total_null_percentage": round(float((df.isna().sum().sum() / total_cells) * 100), 2) if total_cells > 0 else 0.0,
                "columns_with_nulls": int((df.isna().sum() > 0).sum()),
                "columns_fully_null": int(len(empty_columns)),
            },
            "statistical_summary": {
                "numeric_columns_count": int(len(numeric_cols)),
                "categorical_columns_count": int(len(categorical_cols)),
                "datetime_columns_count": int(len(datetime_cols)),
            },
            "column_profiles": column_profiles,
        },
        "column_summary": {},
        "semantic_report": {},
        "identifier_results": {"identifiers": []},
        "anomaly_report": {"anomalies": anomalies, "total_anomalies": int(len(anomalies))},
        "merged_dataset_shape": [total_rows, total_columns],
    }


def _generate_pairs_fallback(
    aux_df: pd.DataFrame,
    anon_df: pd.DataFrame,
    qi_list: List[str],
    output_dir: Path,
) -> Dict[str, Any]:
    common_cols = [c for c in aux_df.columns if c in anon_df.columns]
    usable_qis = [c for c in qi_list if c in common_cols]
    if not usable_qis:
        usable_qis = common_cols[: min(3, len(common_cols))]

    n = min(len(aux_df), len(anon_df), 2000)
    if n < 4:
        raise HTTPException(status_code=400, detail="Not enough rows to generate fallback pairs.")

    aux_sample = aux_df[usable_qis].head(n).reset_index(drop=True)
    anon_sample = anon_df[usable_qis].head(n).reset_index(drop=True)
    anon_shuffled = anon_sample.sample(frac=1.0, random_state=42).reset_index(drop=True)

    def _pair_row(aux_row: pd.Series, anon_row: pd.Series, label: int, idx: int) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "pair_index": idx,
            "aux_index": int(idx),
            "anon_index": int(idx),
            "orig_id": int(idx),
            "anon_id": int(idx),
            "label": int(label),
        }
        equal_flags: List[float] = []
        for col in usable_qis:
            a = aux_row[col]
            b = anon_row[col]
            if pd.isna(a) or pd.isna(b):
                row[f"{col}_equal"] = 0.0
                row[f"{col}_diff"] = 1.0
                equal_flags.append(0.0)
                continue
            try:
                af = float(a)
                bf = float(b)
                diff = abs(af - bf)
                eq = 1.0 if diff == 0 else 0.0
                row[f"{col}_diff"] = float(diff)
                row[f"{col}_equal"] = eq
                equal_flags.append(eq)
            except Exception:
                eq = 1.0 if str(a) == str(b) else 0.0
                row[f"{col}_diff"] = 0.0 if eq == 1.0 else 1.0
                row[f"{col}_equal"] = eq
                equal_flags.append(eq)
        row["similarity_score"] = float(np.mean(equal_flags)) if equal_flags else 0.0
        return row

    positive_rows = [_pair_row(aux_sample.iloc[i], anon_sample.iloc[i], 1, i) for i in range(n)]
    negative_rows = [_pair_row(aux_sample.iloc[i], anon_shuffled.iloc[i], 0, i + n) for i in range(n)]

    pairs_df = pd.DataFrame(positive_rows + negative_rows)
    pairs_df = pairs_df.sample(frac=1.0, random_state=42).reset_index(drop=True)

    split_idx = max(2, int(len(pairs_df) * 0.8))
    train_df = pairs_df.iloc[:split_idx].copy()
    test_df = pairs_df.iloc[split_idx:].copy()

    output_dir.mkdir(parents=True, exist_ok=True)
    pair_path = output_dir / "pair_dataset.csv"
    train_path = output_dir / "train_pairs.csv"
    test_path = output_dir / "test_pairs.csv"
    all_pairs_path = output_dir / "all_pairs.csv"

    pairs_df.to_csv(pair_path, index=False)
    pairs_df.to_csv(all_pairs_path, index=False)
    train_df.to_csv(train_path, index=False)
    test_df.to_csv(test_path, index=False)

    return {
        "fallback_mode": True,
        "fallback_reason": "Agent3 failed or unavailable; generated simplified pairs in routes.py",
        "usable_qis": usable_qis,
        "total_pairs": int(len(pairs_df)),
        "train_pairs": int(len(train_df)),
        "test_pairs": int(len(test_df)),
        "pair_dataset_path": str(pair_path),
        "train_pairs_path": str(train_path),
        "test_pairs_path": str(test_path),
    }


def _write_llm_fallback_outputs(risk_path: Path, llm_dir: Path, num_examples: int) -> Dict[str, Any]:
    llm_dir.mkdir(parents=True, exist_ok=True)
    risk_df = pd.read_csv(risk_path).fillna(0)

    score_candidates = [
        "final_risk_score",
        "final_risk_score_0_1",
        "risk_score",
        "max_attack_score",
        "mean_attack_score",
        "ml_attack_risk",
        "attack_score",
    ]
    score_col = next((c for c in score_candidates if c in risk_df.columns), None)
    if score_col is None:
        numeric_cols = risk_df.select_dtypes(include=[np.number]).columns.tolist()
        score_col = numeric_cols[0] if numeric_cols else None

    if score_col is None:
        explanations: List[Dict[str, Any]] = []
        summary = "Risk summary unavailable: no numeric risk column found in risk file."
    else:
        id_col = "anon_index" if "anon_index" in risk_df.columns else ("anon_id" if "anon_id" in risk_df.columns else None)
        ranked = risk_df.sort_values(by=score_col, ascending=False).head(max(1, int(num_examples)))
        explanations = []
        for idx, row in ranked.iterrows():
            rid = str(row[id_col]) if id_col else str(idx)
            score = float(row[score_col])
            if score > 1.0:
                score = score / 100.0
            level = "HIGH" if score >= 0.75 else ("MEDIUM" if score >= 0.40 else "LOW")
            explanations.append(
                {
                    "record_id": rid,
                    "risk_score": score,
                    "explanation": (
                        f"This record is classified as {level} risk based on model score ({score:.4f}). "
                        "SHAP/LLM explanation was unavailable, so this is a fallback summary from available risk outputs."
                    ),
                }
            )

        summary = (
            f"Fallback risk summary generated without SHAP/LLM. "
            f"Total records: {len(risk_df)}. "
            f"Average {score_col}: {float(risk_df[score_col].mean()):.4f}."
        )

    exp_path = llm_dir / "record_explanations.json"
    summary_path = llm_dir / "dataset_summary.txt"
    report_md_path = llm_dir / "explanations_report.md"

    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(explanations, f, ensure_ascii=False, indent=2)
    summary_path.write_text(summary, encoding="utf-8")
    report_md_path.write_text(f"# Fallback LLM Report\n\n{summary}\n", encoding="utf-8")

    return {
        "fallback_mode": True,
        "fallback_reason": "Generated from risk scores only (SHAP/LLM unavailable)",
        "record_explanations_path": str(exp_path),
        "dataset_summary_path": str(summary_path),
        "report_markdown_path": str(report_md_path),
        "records_generated": len(explanations),
    }


def _normalize_llm_explanations(explanations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(explanations):
        record_id = item.get("record_id")
        if record_id is None:
            record_id = item.get("anon_id")
        if record_id is None:
            record_id = item.get("record_rank")
        if record_id is None:
            record_id = idx + 1

        normalized.append(
            {
                "record_id": str(record_id),
                "risk_score": float(item.get("risk_score", 0.0)),
                "explanation": str(item.get("explanation", "No explanation available.")),
            }
        )
    return normalized


def _get_row_by_index(df: pd.DataFrame, idx: int) -> Optional[pd.Series]:
    if idx in df.index:
        return df.loc[idx]
    if 0 <= idx < len(df):
        return df.iloc[idx]
    return None


# -----------------------------------------------------------------------------
# Basic session endpoints
# -----------------------------------------------------------------------------
@router.get("/session/{session_id}")
async def get_session_info(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    return {
        "session_id": session_id,
        "columns": session.get("columns", []),
        "shape": session.get("shape"),
        "quasi_identifiers": session.get("quasi_identifiers", []),
        "sensitive_attributes": session.get("sensitive_attributes", []),
        "has_analysis": session.get("analysis_results") is not None,
        "has_anonymized_data": session.get("anonymized_df") is not None,
    }


@router.post("/compare")
async def compare_datasets(session_id: str = Form(...)):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    original_df = session.get("df")
    anonymized_df = session.get("anonymized_df")
    quasi_identifiers = session.get("quasi_identifiers", [])

    if original_df is None:
        raise HTTPException(status_code=400, detail="Original dataset not available in session.")
    if anonymized_df is None:
        raise HTTPException(status_code=400, detail="No anonymized data available. Run anonymization first.")
    if len(anonymized_df) == 0:
        raise HTTPException(status_code=400, detail="Anonymized dataset is empty.")

    anonymized_sample = anonymized_df.head(20).to_dict("records")
    anonymized_sample = _safe_json(anonymized_sample)

    comparison_results = {
        "original_shape": [int(original_df.shape[0]), int(original_df.shape[1])],
        "anonymized_shape": [int(anonymized_df.shape[0]), int(anonymized_df.shape[1])],
        "columns": original_df.columns.tolist(),
        "quasi_identifiers": quasi_identifiers,
        "column_comparison": [],
        "sample_comparison": [],
        "statistics_comparison": {},
        "anonymized_sample": anonymized_sample,
    }

    for col in original_df.columns:
        if col not in anonymized_df.columns:
            continue
        orig_col = original_df[col]
        anon_col = anonymized_df[col]

        col_info = {
            "column_name": col,
            "is_quasi_identifier": col in quasi_identifiers,
            "original_unique": int(orig_col.nunique(dropna=True)),
            "anonymized_unique": int(anon_col.nunique(dropna=True)),
            "original_null": int(orig_col.isna().sum()),
            "anonymized_null": int(anon_col.isna().sum()),
            "data_type": str(orig_col.dtype),
            "changes_detected": False,
            "suppressed_values": 0,
        }

        if anon_col.dtype == "object":
            suppressed = int((anon_col == "*").sum())
            col_info["suppressed_values"] = suppressed
            if suppressed > 0:
                col_info["changes_detected"] = True

        changed = int((orig_col.astype(str) != anon_col.astype(str)).sum())
        col_info["changed_values"] = changed
        if changed > 0:
            col_info["changes_detected"] = True

        comparison_results["column_comparison"].append(col_info)

    sample_rows = min(10, len(original_df))
    for idx in range(sample_rows):
        row_comparison = {
            "row_index": idx,
            "original": _safe_json(original_df.iloc[idx].to_dict()),
            "anonymized": _safe_json(anonymized_df.iloc[idx].to_dict()),
            "differences": [],
        }
        for col in original_df.columns:
            if col in quasi_identifiers and col in anonymized_df.columns:
                if str(original_df.iloc[idx][col]) != str(anonymized_df.iloc[idx][col]):
                    row_comparison["differences"].append(col)
        comparison_results["sample_comparison"].append(row_comparison)

    if quasi_identifiers:
        existing_qi = [c for c in quasi_identifiers if c in original_df.columns and c in anonymized_df.columns]
        if existing_qi:
            orig_qi_combinations = original_df[existing_qi].drop_duplicates().shape[0]
            anon_qi_combinations = anonymized_df[existing_qi].drop_duplicates().shape[0]
            comparison_results["statistics_comparison"] = {
                "original_unique_qi_combinations": int(orig_qi_combinations),
                "anonymized_unique_qi_combinations": int(anon_qi_combinations),
                "combination_reduction": float((1 - anon_qi_combinations / orig_qi_combinations) * 100) if orig_qi_combinations > 0 else 0.0,
                "total_qi_cells": int(len(original_df) * len(existing_qi)),
                "suppressed_qi_cells": int((anonymized_df[existing_qi] == "*").sum().sum()),
                "modified_qi_rows": int((anonymized_df[existing_qi].astype(str) != original_df[existing_qi].astype(str)).any(axis=1).sum()),
            }

    return _safe_json(comparison_results)


@router.get("/download-anonymized")
async def download_anonymized(session_id: str, format: str = "csv"):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    anon_df = session.get("anonymized_df")
    if anon_df is None:
        raise HTTPException(status_code=400, detail="No anonymized data available. Run anonymization first.")

    temp_dir = BASE_DIR
    if format == "csv":
        output_path = temp_dir / f"temp_anon_{session_id}.csv"
        anon_df.to_csv(output_path, index=False)
        return FileResponse(str(output_path), filename=f"anonymized_data_{session_id}.csv", media_type="text/csv")

    if format == "excel":
        output_path = temp_dir / f"temp_anon_{session_id}.xlsx"
        anon_df.to_excel(output_path, index=False)
        return FileResponse(
            str(output_path),
            filename=f"anonymized_data_{session_id}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    raise HTTPException(status_code=400, detail="Invalid format. Use 'csv' or 'excel'.")


# -----------------------------------------------------------------------------
# Agent 1: Inspect
# -----------------------------------------------------------------------------
@router.post("/inspect")
async def inspect_data(session_id: str = Form(...)):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    aux_df = session.get("auxiliary_df")
    df_to_inspect = aux_df if aux_df is not None else session.get("df")
    if df_to_inspect is None:
        raise HTTPException(status_code=400, detail="No dataset found in session")

    if not _HAS_AGENT1:
        fallback = _basic_inspection_fallback(df_to_inspect)
        return _safe_json(_normalize_inspection_output(fallback))

    csv_filename = f"auxiliary_{session_id}.csv" if aux_df is not None else f"original_{session_id}.csv"
    csv_path = _session_to_csv(df_to_inspect, csv_filename)
    output_dir = BASE_DIR / "data" / "agent1_output" / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        inspector = DataInspector(output_dir=output_dir)
        results = inspector.run_full_inspection(file_paths=[csv_path], generate_reports=True, save_merged=True)
        return _safe_json(_normalize_inspection_output(results))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inspection error: {e}")


# -----------------------------------------------------------------------------
# Agent 2: Validate identifiers
# -----------------------------------------------------------------------------
@router.post("/validate-identifiers")
async def validate_identifiers(
    session_id: str = Form(...),
    quasi_identifiers: str = Form("[]"),
    direct_identifiers: str = Form("[]"),
    sensitive_attributes: str = Form("[]"),
):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    aux_df = session.get("auxiliary_df")
    anon_df = session.get("anonymized_df")

    if aux_df is None:
        raise HTTPException(status_code=400, detail="Auxiliary dataset required. Upload auxiliary file first.")
    if anon_df is None:
        raise HTTPException(status_code=400, detail="Anonymized dataset required. Run anonymization first.")

    try:
        qi_list = json.loads(quasi_identifiers)
        di_list = json.loads(direct_identifiers)
        sa_list = json.loads(sensitive_attributes)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"JSON parse error: {e}")

    if not _HAS_AGENT2:
        valid_qis = [c for c in qi_list if c in aux_df.columns and c in anon_df.columns]
        invalid_qis = [c for c in qi_list if c not in valid_qis]
        return _safe_json(
            {
                "fallback_mode": True,
                "fallback_reason": "Agent2 not available; basic column validation used",
                "validation": {
                    "quasi_identifiers": {
                        "valid": valid_qis,
                        "invalid": invalid_qis,
                        "is_valid": len(valid_qis) > 0 and len(invalid_qis) == 0,
                    }
                },
                "final_config": {
                    "direct_identifiers": di_list,
                    "quasi_identifiers": valid_qis,
                    "sensitive_attributes": sa_list,
                    "column_mapping": {},
                    "suggested_mappings": {},
                },
            }
        )

    try:
        manager = IdentifierManager(data_dir=str(BASE_DIR / "data"))
        user_config = {
            "direct_identifiers": di_list,
            "quasi_identifiers": qi_list,
            "sensitive_attributes": sa_list,
            "identifier_mapping": {},
            "quasi_identifier_mapping": {},
        }
        result = manager.process_identifiers(aux_df=aux_df, anon_df=anon_df, user_config=user_config, mode="user")
        return _safe_json(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Identifier validation error: {e}")


# -----------------------------------------------------------------------------
# Auxiliary upload controls
# -----------------------------------------------------------------------------
@router.post("/upload-auxiliary")
async def upload_auxiliary(session_id: str = Form(...), file: UploadFile = File(...)):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    fname = (file.filename or "").lower()
    if not (fname.endswith(".csv") or fname.endswith(".xlsx") or fname.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Only CSV or Excel files are accepted")

    try:
        content = await file.read()
        import io

        aux_df = pd.read_csv(io.BytesIO(content)) if fname.endswith(".csv") else pd.read_excel(io.BytesIO(content))
        if aux_df.empty:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        _sessions[session_id]["auxiliary_df"] = aux_df
        _sessions[session_id]["auxiliary_filename"] = file.filename

        return {
            "message": "Auxiliary dataset uploaded successfully",
            "filename": file.filename,
            "rows": int(len(aux_df)),
            "columns": aux_df.columns.tolist(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auxiliary upload error: {e}")


@router.post("/clear-auxiliary")
async def clear_auxiliary(session_id: str = Form(...)):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    _sessions[session_id].pop("auxiliary_df", None)
    _sessions[session_id].pop("auxiliary_filename", None)
    return {"message": "Auxiliary dataset cleared"}


@router.get("/auxiliary-status/{session_id}")
async def auxiliary_status(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    has_custom = "auxiliary_df" in session and session["auxiliary_df"] is not None
    orig_df = session.get("df")
    anon_df = session.get("anonymized_df")

    return {
        "has_custom_auxiliary": has_custom,
        "auxiliary_filename": session.get("auxiliary_filename"),
        "auxiliary_rows": int(len(session["auxiliary_df"])) if has_custom else None,
        "auxiliary_columns": session["auxiliary_df"].columns.tolist() if has_custom else None,
        "session_original_rows": int(len(orig_df)) if orig_df is not None else None,
        "session_original_columns": orig_df.columns.tolist() if orig_df is not None else None,
        "has_anonymized_data": anon_df is not None,
        "anonymized_rows": int(len(anon_df)) if anon_df is not None else None,
        "quasi_identifiers_from_session": session.get("quasi_identifiers", []),
    }


# -----------------------------------------------------------------------------
# Agent 3: Pair generation
# -----------------------------------------------------------------------------
@router.post("/generate-pairs")
async def generate_pairs(
    session_id: str = Form(...),
    quasi_identifiers: str = Form("[]"),
    direct_identifiers: str = Form("[]"),
    sensitive_attributes: str = Form("[]"),
    mode: str = Form("auto"),
    attacker_strength: str = Form("strong"),
):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    aux_df = session.get("auxiliary_df")
    anon_df = session.get("anonymized_df")

    if aux_df is None:
        raise HTTPException(status_code=400, detail="Auxiliary dataset required. Upload auxiliary file first.")
    if anon_df is None:
        raise HTTPException(status_code=400, detail="Anonymized dataset required. Run anonymization first.")

    try:
        qi_list = json.loads(quasi_identifiers)
        di_list = json.loads(direct_identifiers)
        sa_list = json.loads(sensitive_attributes)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"JSON parse error: {e}")

    if not qi_list:
        qi_list = session.get("quasi_identifiers", [])

    output_dir = BASE_DIR / "data" / "pairs" / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    if not _HAS_AGENT3:
        return _safe_json(_generate_pairs_fallback(aux_df, anon_df, qi_list, output_dir))

    try:
        aux_path = _session_to_csv(aux_df, f"aux_{session_id}.csv")
        anon_path = _session_to_csv(anon_df, f"anon_{session_id}.csv")

        agent2_config = {
            "direct_identifiers": di_list,
            "quasi_identifiers": qi_list,
            "sensitive_attributes": sa_list,
            "column_mapping": {},
            "suggested_mappings": {},
            "mode": mode,
            "attacker_strength": attacker_strength,
        }

        generator = PairGenerator(output_dir=output_dir)
        result = generator.run(auxiliary_path=aux_path, anonymized_path=anon_path, agent2_config=agent2_config)
        return _safe_json(result)
    except Exception:
        return _safe_json(_generate_pairs_fallback(aux_df, anon_df, qi_list, output_dir))


# -----------------------------------------------------------------------------
# Agent 4: ML attack
# -----------------------------------------------------------------------------
@router.post("/run-attack")
async def run_attack(session_id: str = Form(...), model_names: str = Form('["logreg","rf","gbm"]')):
    if not _HAS_AGENT4:
        raise HTTPException(status_code=503, detail="Agent4 (MLAttackModel) is not available")

    try:
        models = json.loads(model_names)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"JSON parse error: {e}")

    pairs_dir = BASE_DIR / "data" / "pairs" / session_id
    attack_dir = BASE_DIR / "data" / "attack_models" / session_id
    train_path = pairs_dir / "train_pairs.csv"
    test_path = pairs_dir / "test_pairs.csv"

    if not train_path.exists() or not test_path.exists():
        raise HTTPException(status_code=400, detail="Pair files not found. Run /generate-pairs first")

    try:
        attack_dir.mkdir(parents=True, exist_ok=True)
        attacker = MLAttackModel(train_path=train_path, test_path=test_path, output_dir=attack_dir, model_names=models)
        result = attacker.run()
        return _safe_json(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ML attack error: {e}")


# -----------------------------------------------------------------------------
# Agent 5a: Risk score
# -----------------------------------------------------------------------------
@router.post("/score-risk")
async def score_risk(session_id: str = Form(...)):
    if not _HAS_AGENT5:
        raise HTTPException(status_code=503, detail="Agent5 (RiskScorer) is not available")

    pairs_dir = BASE_DIR / "data" / "pairs" / session_id
    attack_dir = BASE_DIR / "data" / "attack_models" / session_id
    scores_dir = BASE_DIR / "data" / "risk_scores" / session_id

    pair_path = _resolve_pair_dataset_path(pairs_dir)
    model_path = attack_dir / "best_attack_model.pkl"

    if not pair_path.exists():
        raise HTTPException(status_code=400, detail="Pair dataset not found. Run /generate-pairs first")
    if not model_path.exists():
        raise HTTPException(status_code=400, detail="best_attack_model.pkl not found. Run /run-attack first")

    try:
        scores_dir.mkdir(parents=True, exist_ok=True)
        pair_df = pd.read_csv(pair_path)

        if "anon_index" not in pair_df.columns:
            pair_df["anon_index"] = pair_df["anon_id"] if "anon_id" in pair_df.columns else np.arange(len(pair_df))

        if "aux_index" not in pair_df.columns:
            if "orig_id" in pair_df.columns:
                pair_df["aux_index"] = pair_df["orig_id"]
            elif "aux_id" in pair_df.columns:
                pair_df["aux_index"] = pair_df["aux_id"]
            else:
                pair_df["aux_index"] = np.arange(len(pair_df))

        normalized_pair_path = scores_dir / "pair_dataset_for_scoring.csv"
        pair_df.to_csv(normalized_pair_path, index=False)

        scorer = RiskScorer(pairs_path=normalized_pair_path, model_path=model_path, output_dir=scores_dir)
        result = scorer.run()
        return _safe_json(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Risk scoring error: {e}")


# -----------------------------------------------------------------------------
# Agent 5b: Internal risk
# -----------------------------------------------------------------------------
@router.post("/internal-risk")
async def internal_risk(session_id: str = Form(...), quasi_identifiers: str = Form("[]")):
    if not _HAS_INTERNAL:
        raise HTTPException(status_code=503, detail="InternalRiskAnalyzer is not available")
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        qi_list = json.loads(quasi_identifiers)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"JSON parse error: {e}")

    anon_df = _sessions[session_id].get("anonymized_df")
    if anon_df is None:
        raise HTTPException(status_code=400, detail="Anonymized data required. Run anonymization first")

    try:
        anon_path = _session_to_csv(anon_df, f"anon_{session_id}.csv")
        out_dir = BASE_DIR / "data" / "internal_risk" / session_id
        out_dir.mkdir(parents=True, exist_ok=True)

        analyzer = InternalRiskAnalyzer(
            anon_path=anon_path,
            qi_columns=qi_list if qi_list else _sessions[session_id].get("quasi_identifiers", []),
            output_dir=out_dir,
        )
        result = analyzer.run()
        return _safe_json(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal risk error: {e}")


# -----------------------------------------------------------------------------
# Agent 5c: SHAP
# -----------------------------------------------------------------------------
@router.post("/shap-explain")
async def shap_explain(session_id: str = Form(...)):
    shap_dir = BASE_DIR / "data" / "shap_explanations" / session_id
    shap_dir.mkdir(parents=True, exist_ok=True)

    if not _HAS_SHAP:
        return {"fallback_mode": True, "fallback_reason": "SHAPExplainer is not available", "records": []}

    pairs_dir = BASE_DIR / "data" / "pairs" / session_id
    attack_dir = BASE_DIR / "data" / "attack_models" / session_id
    pair_path = _resolve_pair_dataset_path(pairs_dir)
    model_path = attack_dir / "best_attack_model.pkl"

    if not pair_path.exists():
        raise HTTPException(status_code=400, detail="Pair dataset not found. Run /generate-pairs first")
    if not model_path.exists():
        raise HTTPException(status_code=400, detail="best_attack_model.pkl not found. Run /run-attack first")

    try:
        explainer = AttackModelExplainer(model_path=model_path, pairs_path=pair_path, output_dir=shap_dir)
        result = explainer.run()
        return _safe_json(result)
    except Exception:
        return {"fallback_mode": True, "fallback_reason": "SHAP generation failed; continuing without SHAP outputs", "records": []}


# -----------------------------------------------------------------------------
# Agent 6: Aggregate risk
# -----------------------------------------------------------------------------
@router.post("/aggregate-risk")
async def aggregate_risk(session_id: str = Form(...)):
    if not _HAS_AGENT6:
        raise HTTPException(status_code=503, detail="Agent6 (RiskAggregator) is not available")

    scores_dir = BASE_DIR / "data" / "risk_scores" / session_id
    internal_dir = BASE_DIR / "data" / "internal_risk" / session_id
    shap_dir = BASE_DIR / "data" / "shap_explanations" / session_id
    pairs_dir = BASE_DIR / "data" / "pairs" / session_id
    agg_dir = BASE_DIR / "data" / "risk_scores" / session_id / "agent7"

    ml_risk_path = scores_dir / "risk_per_record.csv"
    if not ml_risk_path.exists():
        raise HTTPException(status_code=400, detail="risk_per_record.csv not found. Run /score-risk first")

    internal_path = internal_dir / "internal_risk_per_record.csv"
    shap_global_path = _resolve_shap_global_path(shap_dir)
    pair_path = _resolve_pair_dataset_path(pairs_dir)

    try:
        agg_dir.mkdir(parents=True, exist_ok=True)
        aggregator = RiskAggregator(
            ml_risk_path=ml_risk_path,
            internal_risk_path=internal_path if internal_path.exists() else None,
            shap_global_path=shap_global_path,
            pair_data_path=pair_path if pair_path.exists() else None,
            output_dir=agg_dir,
        )
        result = aggregator.run()
        return _safe_json(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Risk aggregation error: {e}")


# -----------------------------------------------------------------------------
# Agent 7: LLM explain
# -----------------------------------------------------------------------------
@router.post("/explain-risk")
async def explain_risk(
    session_id: str = Form(...),
    openai_api_key: Optional[str] = Form(None),
    model_name: str = Form("gpt-4o-mini"),
    num_examples: int = Form(5),
):
    scores_dir = BASE_DIR / "data" / "risk_scores" / session_id
    shap_dir = BASE_DIR / "data" / "shap_explanations" / session_id
    llm_dir = BASE_DIR / "data" / "llm_explanations" / session_id

    risk_path = scores_dir / "risk_per_record.csv"
    if not risk_path.exists():
        raise HTTPException(status_code=400, detail="risk_per_record.csv not found. Run /score-risk first")

    shap_local_path = shap_dir / "shap_local_explanations.csv"
    shap_global_path = _resolve_shap_global_path(shap_dir)
    shap_available = shap_local_path.exists() and shap_global_path is not None

    if not _HAS_AGENT7 or not shap_available:
        return _safe_json(_write_llm_fallback_outputs(risk_path, llm_dir, num_examples))

    try:
        explainer = LLMExplainer(api_key=openai_api_key, model_name=model_name)
        result = explainer.generate_full_report(
            risk_per_record_path=risk_path,
            shap_local_path=shap_local_path,
            shap_global_path=shap_global_path,
            output_dir=llm_dir,
            num_examples=num_examples,
        )
        return _safe_json(result)
    except Exception:
        return _safe_json(_write_llm_fallback_outputs(risk_path, llm_dir, num_examples))


# -----------------------------------------------------------------------------
# Result endpoints
# -----------------------------------------------------------------------------
@router.get("/results/risk-scores/{session_id}")
async def get_risk_scores_data(session_id: str):
    scores_dir = BASE_DIR / "data" / "risk_scores" / session_id
    for rel in ["risk_per_record.csv", "agent7/final_record_risk.csv", "agent7/final_risk_per_record.csv"]:
        path = scores_dir / rel
        if path.exists():
            df = pd.read_csv(path).fillna(0)
            return {"records": _safe_json(df.to_dict("records")), "columns": df.columns.tolist(), "total": int(len(df))}
    return {"records": [], "columns": [], "total": 0}


@router.get("/results/matched-row-pairs/{session_id}")
async def get_matched_row_pairs(session_id: str, limit: int = Query(default=50, ge=1, le=1000)):
    session = _sessions.get(session_id, {})
    aux_df = session.get("auxiliary_df")
    anon_df = session.get("anonymized_df")

    raw_dir = BASE_DIR / "data" / "raw"
    if aux_df is None:
        for name in [f"aux_{session_id}.csv", f"auxiliary_{session_id}.csv"]:
            path = raw_dir / name
            if path.exists():
                try:
                    aux_df = pd.read_csv(path)
                    break
                except Exception:
                    pass

    if anon_df is None:
        for name in [f"anon_{session_id}.csv", f"anonymized_{session_id}.csv", f"original_{session_id}.csv"]:
            path = raw_dir / name
            if path.exists():
                try:
                    anon_df = pd.read_csv(path)
                    break
                except Exception:
                    pass

    if aux_df is None:
        return {"pairs": [], "total": 0, "message": "Auxiliary rows unavailable in session or saved files."}
    if anon_df is None:
        return {"pairs": [], "total": 0, "message": "Anonymized rows unavailable in session or saved files."}

    pairs_dir = BASE_DIR / "data" / "pairs" / session_id
    pair_path = _resolve_pair_dataset_path(pairs_dir)
    if not pair_path.exists():
        return {"pairs": [], "total": 0, "message": "Pair dataset not found. Run /generate-pairs first."}

    try:
        pair_df = pd.read_csv(pair_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read pair dataset: {e}")

    if "label" in pair_df.columns:
        labels = pair_df["label"].astype(str).str.strip().str.lower()
        matched_df = pair_df[labels.isin({"1", "1.0", "true", "yes"})].copy()
    elif "overall_similarity" in pair_df.columns:
        matched_df = pair_df[pair_df["overall_similarity"] >= 0.6].copy()
    else:
        matched_df = pair_df.copy()

    if matched_df.empty:
        if "overall_similarity" in pair_df.columns:
            matched_df = pair_df.sort_values(by="overall_similarity", ascending=False).head(limit).copy()
        else:
            matched_df = pair_df.head(limit).copy()

    sort_col = "overall_similarity" if "overall_similarity" in matched_df.columns else None
    if sort_col:
        matched_df = matched_df.sort_values(by=sort_col, ascending=False)

    matched_df = matched_df.head(limit)
    output_pairs: List[Dict[str, Any]] = []

    for _, row in matched_df.iterrows():
        aux_idx = int(row.get("aux_index", -1))
        anon_idx = int(row.get("anon_index", -1))

        aux_row = _get_row_by_index(aux_df, aux_idx)
        anon_row = _get_row_by_index(anon_df, anon_idx)
        if aux_row is None or anon_row is None:
            continue

        item: Dict[str, Any] = {
            "aux_index": aux_idx,
            "anon_index": anon_idx,
            "auxiliary_row": _safe_json(aux_row.to_dict()),
            "anonymized_row": _safe_json(anon_row.to_dict()),
        }

        if "overall_similarity" in row:
            item["overall_similarity"] = _safe_json(float(row.get("overall_similarity", 0.0)))
        if "attack_score" in row:
            item["attack_score"] = _safe_json(float(row.get("attack_score", 0.0)))

        output_pairs.append(item)

    return {"pairs": output_pairs, "total": int(len(output_pairs))}


@router.get("/results/shap-global/{session_id}")
async def get_shap_global_data(session_id: str):
    shap_dir = BASE_DIR / "data" / "shap_explanations" / session_id
    shap_path = _resolve_shap_global_path(shap_dir)
    if shap_path is None:
        return {"records": [], "columns": []}
    df = pd.read_csv(shap_path).fillna(0)
    return {"records": _safe_json(df.to_dict("records")), "columns": df.columns.tolist()}


@router.get("/results/shap-local/{session_id}")
async def get_shap_local_data(session_id: str):
    path = BASE_DIR / "data" / "shap_explanations" / session_id / "shap_local_explanations.csv"
    if not path.exists():
        return {"records": [], "columns": []}

    df = pd.read_csv(path).fillna(0)

    # Normalize to frontend expected long format: anon_id, feature, shap_value
    if {"anon_id", "feature", "shap_value"}.issubset(set(df.columns)):
        out_df = df[["anon_id", "feature", "shap_value"]].copy()
    else:
        id_col = "anon_index" if "anon_index" in df.columns else ("anon_id" if "anon_id" in df.columns else None)
        shap_cols = [c for c in df.columns if str(c).startswith("shap__")]
        rows: List[Dict[str, Any]] = []
        if id_col and shap_cols:
            for _, row in df.iterrows():
                anon_id = row[id_col]
                for col in shap_cols:
                    rows.append(
                        {
                            "anon_id": anon_id,
                            "feature": col.replace("shap__", ""),
                            "shap_value": float(row[col]),
                        }
                    )
        out_df = pd.DataFrame(rows)

    return {"records": _safe_json(out_df.to_dict("records")), "columns": out_df.columns.tolist()}


@router.get("/results/llm-explanations/{session_id}")
async def get_llm_explanations_data(session_id: str):
    llm_dir = BASE_DIR / "data" / "llm_explanations" / session_id
    exp_path = llm_dir / "record_explanations.json"
    summary_path = llm_dir / "dataset_summary.txt"

    if not exp_path.exists():
        raise HTTPException(status_code=404, detail="LLM explanations not found. Run /explain-risk first")

    with open(exp_path, "r", encoding="utf-8") as f:
        explanations = json.load(f)

    normalized = _normalize_llm_explanations(explanations if isinstance(explanations, list) else [])
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else None
    return {"explanations": normalized, "dataset_summary": summary}


@router.get("/results/risk-summary/{session_id}")
async def get_risk_summary_data(session_id: str):
    scores_dir = BASE_DIR / "data" / "risk_scores" / session_id
    candidates = [
        scores_dir / "agent7" / "global_risk_summary.json",
        scores_dir / "risk_summary.json",
        scores_dir / "agent7" / "global_summary.json",
    ]
    for path in candidates:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    raise HTTPException(status_code=404, detail="Risk summary not found")


# -----------------------------------------------------------------------------
# Pipeline status
# -----------------------------------------------------------------------------
@router.get("/pipeline-status/{session_id}")
async def pipeline_status(session_id: str):
    pairs_dir = BASE_DIR / "data" / "pairs" / session_id
    attack_dir = BASE_DIR / "data" / "attack_models" / session_id
    scores_dir = BASE_DIR / "data" / "risk_scores" / session_id
    internal_dir = BASE_DIR / "data" / "internal_risk" / session_id
    shap_dir = BASE_DIR / "data" / "shap_explanations" / session_id
    agg_dir = BASE_DIR / "data" / "risk_scores" / session_id / "agent7"
    llm_dir = BASE_DIR / "data" / "llm_explanations" / session_id

    pair_dataset_exists = (
        (pairs_dir / "pair_dataset.csv").exists()
        or (pairs_dir / "all_pairs.csv").exists()
        or ((pairs_dir / "train_pairs.csv").exists() and (pairs_dir / "test_pairs.csv").exists())
    )
    shap_global_exists = _resolve_shap_global_path(shap_dir) is not None
    llm_exists = (llm_dir / "explanations_report.md").exists() or (llm_dir / "record_explanations.json").exists()

    return {
        "session_id": session_id,
        "steps": {
            "pairs_generated": pair_dataset_exists,
            "attack_trained": (attack_dir / "best_attack_model.pkl").exists(),
            "risk_scored": (scores_dir / "risk_per_record.csv").exists(),
            "internal_risk": (internal_dir / "internal_risk_per_record.csv").exists(),
            "shap_explained": shap_global_exists,
            "risk_aggregated": (agg_dir / "global_risk_summary.json").exists(),
            "llm_explained": llm_exists,
        },
    }
