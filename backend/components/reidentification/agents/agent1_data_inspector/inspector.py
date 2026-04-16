from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from .column_summarizer import ColumnSummarizer
from .data_profile import DataProfile
from .semantic_analyzer import SemanticAnalyzer
from .survey_merger import SurveyMerger
from ...utils.logger import ensure_dir, get_logger

logger = get_logger("corrected_data_inspector.inspector")


class DataInspector:
    def __init__(
        self,
        output_dir: Optional[Path] = None,
        composite_keys: Optional[List[str]] = None,
        identifier_detector: Optional[Any] = None,
    ) -> None:
        self.output_dir = ensure_dir(output_dir or Path("corrected_data_inspector_output"))
        self.composite_keys = composite_keys or []
        self.identifier_detector = identifier_detector
        self.survey_merger = SurveyMerger()
        self.data_profile = DataProfile()
        self.column_summarizer = ColumnSummarizer()
        self.semantic_analyzer = SemanticAnalyzer()

    def run_full_inspection(
        self,
        file_paths: Sequence[Path],
        generate_reports: bool = True,
        save_merged: bool = True,
    ) -> Dict[str, Any]:
        if not file_paths:
            raise ValueError("No file paths were provided")

        file_paths = [Path(p) for p in file_paths]
        logger.info("Starting inspection for %d file(s)", len(file_paths))

        merged_df, merge_report = self.survey_merger.merge_survey_files(file_paths, composite_keys=self.composite_keys)
        raw_schema = self._schema_validation(merged_df)
        raw_missing = self._missing_value_report(merged_df)
        cleaned_df = self._clean_merged_data(merged_df)

        identifier_results = self._run_identifier_detection(cleaned_df)
        profile_report = self.data_profile.generate_profile(cleaned_df)
        column_summary = self.column_summarizer.summarize_columns(cleaned_df)
        semantic_report = self.semantic_analyzer.analyze_dataframe(cleaned_df, identifier_results)
        anomaly_report = self._anomaly_detection(cleaned_df, identifier_results)

        results: Dict[str, Any] = {
            "merge_report": merge_report,
            "schema_validation": raw_schema,
            "missing_value_report": raw_missing,
            "data_profile": profile_report,
            "column_summary": column_summary,
            "semantic_report": semantic_report,
            "identifier_results": identifier_results,
            "anomaly_report": anomaly_report,
            "merged_dataset_shape": tuple(cleaned_df.shape),
        }

        if save_merged:
            merged_path = self.output_dir / "merged_dataset.csv"
            cleaned_df.to_csv(merged_path, index=False)
            results["merged_dataset_path"] = str(merged_path)

        if generate_reports:
            self._save_reports(results)

        return results

    def _run_identifier_detection(self, df: pd.DataFrame) -> Dict[str, Any]:
        if self.identifier_detector is None:
            return {"identifiers": []}

        detector = self.identifier_detector
        if hasattr(detector, "detect"):
            result = detector.detect(df)
        elif callable(detector):
            result = detector(df)
        else:
            raise TypeError("identifier_detector must be callable or expose a detect(df) method")

        if result is None:
            return {"identifiers": []}
        if isinstance(result, list):
            return {"identifiers": [c for c in result if c in df.columns]}
        if isinstance(result, dict):
            ids = result.get("identifiers") or result.get("identifier_columns") or []
            result = dict(result)
            result["identifiers"] = [c for c in ids if c in df.columns]
            return result
        raise TypeError("identifier detector output must be dict, list, or None")

    def _clean_merged_data(self, df: pd.DataFrame) -> pd.DataFrame:
        cleaned = df.copy()

        if cleaned.columns.duplicated().any():
            cleaned = cleaned.loc[:, ~cleaned.columns.duplicated()].copy()

        for col in cleaned.columns:
            series = cleaned[col]
            if pd.api.types.is_object_dtype(series) or str(series.dtype).startswith("string"):
                cleaned[col] = series.astype("string")

        return cleaned

    def _schema_validation(self, df: pd.DataFrame) -> Dict[str, Any]:
        duplicate_columns = df.columns[df.columns.duplicated()].tolist()
        empty_columns = [col for col in df.columns if df[col].isna().all()]
        constant_columns = [col for col in df.columns if df[col].dropna().nunique() <= 1 and not df[col].dropna().empty]
        high_null_columns = [
            {"column": col, "null_rate": round(float(df[col].isna().mean()), 3)}
            for col in df.columns
            if float(df[col].isna().mean()) > 0.9
        ]
        issues = len(duplicate_columns) + len(empty_columns) + len(constant_columns) + len(high_null_columns)
        return {
            "total_columns": int(df.shape[1]),
            "total_rows": int(df.shape[0]),
            "duplicate_columns": duplicate_columns,
            "empty_columns": empty_columns,
            "constant_columns": constant_columns,
            "high_null_columns": high_null_columns,
            "validation_passed": issues == 0,
            "issues_found": issues,
        }

    def _missing_value_report(self, df: pd.DataFrame) -> Dict[str, Any]:
        by_column = {
            col: {
                "missing_count": int(df[col].isna().sum()),
                "missing_pct": round(float(df[col].isna().mean() * 100.0), 2),
            }
            for col in df.columns
        }
        total_cells = max(int(df.shape[0] * df.shape[1]), 1)
        total_missing = int(df.isna().sum().sum())
        return {
            "total_missing": total_missing,
            "missing_pct_overall": round(total_missing / total_cells * 100.0, 2),
            "by_column": by_column,
        }

    def _anomaly_detection(self, df: pd.DataFrame, identifier_results: Dict[str, Any]) -> Dict[str, Any]:
        identifier_columns = set(identifier_results.get("identifiers", []))
        numeric_outliers: Dict[str, Dict[str, Any]] = {}
        categorical_alerts: Dict[str, Dict[str, Any]] = {}

        for col in df.columns:
            if col in identifier_columns:
                continue
            series = df[col]
            non_null = series.dropna()
            if non_null.empty:
                continue
            if pd.api.types.is_numeric_dtype(series):
                q1 = float(non_null.quantile(0.25))
                q3 = float(non_null.quantile(0.75))
                iqr = q3 - q1
                if iqr == 0:
                    continue
                lower = q1 - 3.0 * iqr
                upper = q3 + 3.0 * iqr
                mask = (non_null < lower) | (non_null > upper)
                count = int(mask.sum())
                if count > 0:
                    numeric_outliers[col] = {
                        "outlier_count": count,
                        "outlier_pct": round(count / len(non_null) * 100.0, 2),
                        "lower_bound": lower,
                        "upper_bound": upper,
                    }
            elif not pd.api.types.is_datetime64_any_dtype(series):
                unique_ratio = non_null.nunique() / max(len(series), 1)
                value_counts = non_null.astype(str).value_counts(normalize=True)
                rare_count = int((value_counts < 0.01).sum())
                if unique_ratio > 0.95 or rare_count > 0:
                    categorical_alerts[col] = {
                        "unique_ratio": round(unique_ratio, 4),
                        "rare_category_count": rare_count,
                        "top_values": value_counts.head(10).round(4).to_dict(),
                    }

        return {
            "numeric_outliers": numeric_outliers,
            "categorical_alerts": categorical_alerts,
        }

    def _save_reports(self, reports: Dict[str, Any]) -> None:
        for name, report in reports.items():
            if name == "merged_dataset_path":
                continue
            path = self.output_dir / f"{name}.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._json_safe(report), fh, indent=2, ensure_ascii=False)

    def _json_safe(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {str(k): self._json_safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._json_safe(v) for v in obj]
        if isinstance(obj, tuple):
            return [self._json_safe(v) for v in obj]
        if isinstance(obj, pd.Timestamp):
            return str(obj)
        if hasattr(obj, "item"):
            try:
                return obj.item()
            except Exception:
                return str(obj)
        return obj
