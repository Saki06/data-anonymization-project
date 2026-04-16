from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ...utils.logger import get_logger

logger = get_logger("corrected_data_inspector.survey_merger")


class SurveyMerger:
    """Preprocess each uploaded CSV and merge on the safest available common keys."""

    def __init__(self, sample_size: int = 200, max_auto_keys: int = 1) -> None:
        self.sample_size = sample_size
        self.max_auto_keys = max_auto_keys

    def merge_survey_files(
        self,
        file_paths: List[Path],
        composite_keys: Optional[List[str]] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        composite_keys = [self._normalize_column_name(c) for c in (composite_keys or [])]

        if not file_paths:
            raise ValueError("file_paths is empty")

        per_file_reports: List[Dict[str, Any]] = []
        prepared_frames: List[Tuple[Path, pd.DataFrame, Dict[str, Any]]] = []

        for file_path in file_paths:
            df = pd.read_csv(file_path)
            prepared_df, prep_report = self._preprocess_file(df)
            prep_report["file"] = file_path.name
            per_file_reports.append(prep_report)
            prepared_frames.append((file_path, prepared_df, prep_report))
            logger.info("Prepared %s -> %s", file_path.name, prepared_df.shape)

        if len(prepared_frames) == 1:
            single_path, single_df, _ = prepared_frames[0]
            return single_df, {
                "strategy": "single_file",
                "files_merged": 1,
                "files_skipped": [],
                "total_records": int(len(single_df)),
                "total_columns": int(len(single_df.columns)),
                "per_file_reports": per_file_reports,
                "merge_steps": [],
                "base_file": single_path.name,
            }

        base_path, merged_df, _ = prepared_frames[0]
        files_merged = 1
        files_skipped: List[str] = []
        merge_steps: List[Dict[str, Any]] = []

        for idx, (file_path, df, _) in enumerate(prepared_frames[1:], start=2):
            merge_keys, strategy, key_scores = self._choose_merge_keys(
                merged_df,
                df,
                composite_keys=composite_keys,
            )

            if not merge_keys:
                files_skipped.append(file_path.name)
                logger.warning("Skipping %s: no safe common merge keys", file_path.name)
                continue

            before_shape = merged_df.shape

            try:
                merged_df = pd.merge(
                    merged_df,
                    df,
                    on=merge_keys,
                    how="outer",
                    suffixes=("", f"_{idx}"),
                )
                files_merged += 1

                merge_steps.append(
                    {
                        "file": file_path.name,
                        "keys": merge_keys,
                        "strategy": strategy,
                        "key_scores": key_scores,
                        "shape_before": before_shape,
                        "shape_after": merged_df.shape,
                    }
                )

                logger.info(
                    "Merged %s using %s (%s): %s -> %s",
                    file_path.name,
                    merge_keys,
                    strategy,
                    before_shape,
                    merged_df.shape,
                )

            except Exception as exc:
                files_skipped.append(file_path.name)
                logger.exception("Failed to merge %s: %s", file_path.name, exc)

        report = {
            "strategy": "adaptive_preprocessed_outer_merge",
            "base_file": base_path.name,
            "files_merged": files_merged,
            "files_skipped": files_skipped,
            "total_records": int(len(merged_df)),
            "total_columns": int(len(merged_df.columns)),
            "per_file_reports": per_file_reports,
            "merge_steps": merge_steps,
            "max_auto_keys": self.max_auto_keys,
        }

        return merged_df, report

    def _preprocess_file(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        report: Dict[str, Any] = {
            "original_shape": tuple(df.shape),
            "renamed_columns": {},
            "duplicate_columns_detected": 0,
            "duplicate_columns_renamed": 0,
            "duplicate_columns_removed": 0,
            "type_conversions": {},
        }

        cleaned = df.copy()

        normalized_columns: List[str] = []
        seen: Dict[str, int] = {}

        for original in cleaned.columns:
            normalized = self._normalize_column_name(original)
            if not normalized:
                normalized = "unnamed"

            count = seen.get(normalized, 0)
            seen[normalized] = count + 1

            if count > 0:
                report["duplicate_columns_detected"] += 1
                report["duplicate_columns_renamed"] += 1

            final_name = normalized if count == 0 else f"{normalized}_{count + 1}"
            normalized_columns.append(final_name)

            if str(original) != final_name:
                report["renamed_columns"][str(original)] = final_name

        cleaned.columns = normalized_columns

        if cleaned.columns.duplicated().any():
            dup_count = int(cleaned.columns.duplicated().sum())
            cleaned = cleaned.loc[:, ~cleaned.columns.duplicated()].copy()
            report["duplicate_columns_removed"] = dup_count

        for col in cleaned.columns:
            cleaned[col] = self._normalize_series(cleaned[col], report["type_conversions"], col)

        report["final_shape"] = tuple(cleaned.shape)
        return cleaned, report

    def _normalize_series(
        self,
        series: pd.Series,
        conversions: Dict[str, str],
        col: str,
    ) -> pd.Series:
        if pd.api.types.is_numeric_dtype(series):
            return series

        if pd.api.types.is_bool_dtype(series):
            return series

        if pd.api.types.is_datetime64_any_dtype(series):
            return series

        cleaned = series.copy()

        if cleaned.dtype == object or str(cleaned.dtype).startswith("string"):
            cleaned = cleaned.apply(self._clean_string)

            numeric_candidate = pd.to_numeric(cleaned, errors="coerce")
            numeric_ratio = float(numeric_candidate.notna().mean()) if len(cleaned) else 0.0
            if numeric_ratio >= 0.9 and numeric_candidate.notna().sum() > 0:
                conversions[col] = "numeric"
                return numeric_candidate

            datetime_candidate = pd.to_datetime(cleaned, errors="coerce")
            datetime_ratio = float(datetime_candidate.notna().mean()) if len(cleaned) else 0.0
            if datetime_ratio >= 0.9 and datetime_candidate.notna().sum() > 0:
                conversions[col] = "datetime"
                return datetime_candidate

            lowered = cleaned.dropna().astype(str).str.lower()
            if (
                not lowered.empty
                and lowered.isin({"true", "false", "yes", "no", "0", "1"}).mean() >= 0.95
            ):
                conversions[col] = "boolean"
                return cleaned.map(
                    {
                        "true": True,
                        "false": False,
                        "yes": True,
                        "no": False,
                        "1": True,
                        "0": False,
                    }
                )

            return cleaned.astype("string")

        return cleaned

    def _choose_merge_keys(
        self,
        left_df: pd.DataFrame,
        right_df: pd.DataFrame,
        composite_keys: List[str],
    ) -> Tuple[List[str], str, Dict[str, float]]:
        common_cols = [c for c in left_df.columns if c in set(right_df.columns)]

        if composite_keys:
            full = [k for k in composite_keys if k in common_cols]
            if len(full) == len(composite_keys):
                return full, "full_composite_keys", {k: 100.0 for k in full}
            if full:
                return full, "partial_composite_keys", {k: 75.0 for k in full}

        if not common_cols:
            return [], "no_common_columns", {}

        ranked_scores = self._rank_common_columns(left_df, right_df, common_cols)
        if not ranked_scores:
            return [], "no_safe_keys", {}

        sorted_cols = [
            col
            for col, score in sorted(ranked_scores.items(), key=lambda x: x[1], reverse=True)
            if score >= 45.0
        ]

        if not sorted_cols:
            return [], "no_safe_keys", ranked_scores

        top = sorted_cols[: min(self.max_auto_keys, len(sorted_cols))]
        return top, "auto_ranked_common_keys", {k: round(ranked_scores[k], 2) for k in top}

    def _rank_common_columns(
        self,
        left_df: pd.DataFrame,
        right_df: pd.DataFrame,
        common_cols: List[str],
    ) -> Dict[str, float]:
        scored: Dict[str, float] = {}
        n_left = max(len(left_df), 1)
        n_right = max(len(right_df), 1)

        for col in common_cols:
            left = left_df[col]
            right = right_df[col]
            score = 0.0

            if str(left.dtype) == str(right.dtype):
                score += 10.0

            left_unique = left.nunique(dropna=True) / n_left
            right_unique = right.nunique(dropna=True) / n_right
            avg_unique = (left_unique + right_unique) / 2.0
            score += avg_unique * 50.0

            left_null = float(left.isna().mean())
            right_null = float(right.isna().mean())
            score -= ((left_null + right_null) / 2.0) * 20.0

            overlap = self._overlap_ratio(left, right)
            score += overlap * 25.0

            if self._looks_identifierish(col):
                score += 10.0

            scored[col] = score

        return scored

    def _overlap_ratio(self, left: pd.Series, right: pd.Series) -> float:
        left_values = set(left.dropna().astype(str).head(self.sample_size * 5))
        right_values = set(right.dropna().astype(str).head(self.sample_size * 5))

        if not left_values or not right_values:
            return 0.0

        intersection = len(left_values & right_values)
        denominator = min(len(left_values), len(right_values))
        return intersection / denominator if denominator else 0.0

    @staticmethod
    def _normalize_column_name(name: Any) -> str:
        text = str(name).strip().lower()
        text = text.replace("/", "_").replace("-", "_").replace(" ", "_")
        while "__" in text:
            text = text.replace("__", "_")
        return text.strip("_")

    @staticmethod
    def _clean_string(value: Any) -> Any:
        if pd.isna(value):
            return pd.NA

        text = str(value).strip()
        if text == "":
            return pd.NA

        lowered = text.lower()
        if lowered in {"na", "n/a", "null", "none", "nan", "missing", "unknown"}:
            return pd.NA

        return lowered

    @staticmethod
    def _looks_identifierish(name: str) -> bool:
        tokens = ["id", "code", "key", "uid", "guid", "serial", "ref", "no", "number"]
        return any(token in name.lower() for token in tokens)