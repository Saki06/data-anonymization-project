from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from ...utils.logger import get_logger

logger = get_logger("corrected_data_inspector.data_profile")


class DataProfile:
    def generate_profile(self, df: pd.DataFrame) -> Dict[str, Any]:
        logger.info("Generating data profile")
        return {
            "dataset_overview": self._dataset_overview(df),
            "column_profiles": self._column_profiles(df),
            "data_quality": self._data_quality_metrics(df),
            "statistical_summary": self._statistical_summary(df),
        }

    def _dataset_overview(self, df: pd.DataFrame) -> Dict[str, Any]:
        total_cells = int(df.shape[0] * df.shape[1])
        return {
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "total_cells": total_cells,
            "memory_usage_mb": round(df.memory_usage(deep=True).sum() / (1024 * 1024), 3),
            "duplicate_rows": int(df.duplicated().sum()),
            "duplicate_row_pct": round(float(df.duplicated().mean() * 100.0), 2) if len(df) else 0.0,
            "dtype_counts": {str(k): int(v) for k, v in df.dtypes.astype(str).value_counts().to_dict().items()},
        }

    def _column_profiles(self, df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        profiles: Dict[str, Dict[str, Any]] = {}
        for col in df.columns:
            series = df[col]
            non_null = series.dropna()
            profile: Dict[str, Any] = {
                "dtype": str(series.dtype),
                "dtype_group": self._dtype_group(series),
                "non_null_count": int(non_null.shape[0]),
                "null_count": int(series.isna().sum()),
                "null_pct": round(float(series.isna().mean() * 100.0), 2) if len(series) else 0.0,
                "unique_count": int(non_null.nunique()),
                "unique_pct": round(float(non_null.nunique() / len(series) * 100.0), 2) if len(series) else 0.0,
            }

            if pd.api.types.is_numeric_dtype(series):
                profile.update(self._numeric_profile(non_null))
            elif pd.api.types.is_datetime64_any_dtype(series):
                profile.update(self._datetime_profile(non_null))
            else:
                profile.update(self._string_profile(non_null))
            profiles[col] = profile
        return profiles

    def _data_quality_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        total_cells = max(int(df.shape[0] * df.shape[1]), 1)
        missing_cells = int(df.isna().sum().sum())
        return {
            "completeness_pct": round((1 - missing_cells / total_cells) * 100.0, 2),
            "missing_cells": missing_cells,
            "columns_with_missing": [c for c in df.columns if df[c].isna().any()],
            "fully_empty_columns": [c for c in df.columns if df[c].isna().all()],
            "constant_columns": [c for c in df.columns if df[c].dropna().nunique() <= 1 and len(df[c].dropna()) > 0],
        }

    def _statistical_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        numeric_df = df.select_dtypes(include=["number"])
        if numeric_df.empty:
            return {"numeric_summary": {}}
        sampled = numeric_df.sample(min(len(numeric_df), 100000), random_state=42) if len(numeric_df) > 100000 else numeric_df
        summary = sampled.describe(percentiles=[0.25, 0.5, 0.75]).round(4)
        return {"numeric_summary": summary.to_dict()}

    @staticmethod
    def _dtype_group(series: pd.Series) -> str:
        if pd.api.types.is_bool_dtype(series):
            return "boolean"
        if pd.api.types.is_numeric_dtype(series):
            return "numeric"
        if pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"
        return "categorical"

    @staticmethod
    def _numeric_profile(non_null: pd.Series) -> Dict[str, Any]:
        if non_null.empty:
            return {}
        return {
            "min": float(non_null.min()),
            "max": float(non_null.max()),
            "mean": float(non_null.mean()),
            "median": float(non_null.median()),
            "std": float(non_null.std()) if len(non_null) > 1 else 0.0,
            "q1": float(non_null.quantile(0.25)),
            "q3": float(non_null.quantile(0.75)),
        }

    @staticmethod
    def _datetime_profile(non_null: pd.Series) -> Dict[str, Any]:
        if non_null.empty:
            return {}
        return {
            "min_date": str(non_null.min()),
            "max_date": str(non_null.max()),
            "date_range_days": int((non_null.max() - non_null.min()).days) if len(non_null) > 1 else 0,
        }

    @staticmethod
    def _string_profile(non_null: pd.Series) -> Dict[str, Any]:
        if non_null.empty:
            return {}
        as_str = non_null.astype(str)
        lengths = as_str.str.len()
        value_counts = as_str.value_counts(dropna=True)
        top_values = value_counts.head(10).to_dict()
        return {
            "avg_length": float(lengths.mean()),
            "min_length": int(lengths.min()),
            "max_length": int(lengths.max()),
            "most_frequent": as_str.mode().iloc[0] if not as_str.mode().empty else None,
            "top_values": top_values,
        }
