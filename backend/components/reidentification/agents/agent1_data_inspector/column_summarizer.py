from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from ...utils.logger import get_logger

logger = get_logger("corrected_data_inspector.column_summarizer")


class ColumnSummarizer:
    def summarize_columns(self, df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        logger.info("Generating column summaries")
        return {col: self._summarize_column(df[col]) for col in df.columns}

    def _summarize_column(self, series: pd.Series) -> Dict[str, Any]:
        non_null = series.dropna()
        total = len(series)
        summary: Dict[str, Any] = {
            "dtype": str(series.dtype),
            "total_values": int(total),
            "non_null_values": int(non_null.shape[0]),
            "null_count": int(series.isna().sum()),
            "null_pct": round(float(series.isna().mean() * 100.0), 2) if total else 0.0,
            "unique_values": int(non_null.nunique()),
            "unique_ratio": round(float(non_null.nunique() / total), 4) if total else 0.0,
            "completeness_score": round(float(1 - series.isna().mean()), 4) if total else 0.0,
        }

        if pd.api.types.is_numeric_dtype(series):
            summary.update(self._numeric_summary(non_null))
        elif pd.api.types.is_datetime64_any_dtype(series):
            summary.update(self._datetime_summary(non_null))
        else:
            summary.update(self._categorical_summary(non_null, total))
        return summary

    def _numeric_summary(self, non_null: pd.Series) -> Dict[str, Any]:
        if non_null.empty:
            return {}
        q1 = float(non_null.quantile(0.25))
        q3 = float(non_null.quantile(0.75))
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        extreme_lower = q1 - 3.0 * iqr
        extreme_upper = q3 + 3.0 * iqr
        outliers = int(((non_null < lower) | (non_null > upper)).sum())
        extreme_outliers = int(((non_null < extreme_lower) | (non_null > extreme_upper)).sum())
        return {
            "min": float(non_null.min()),
            "max": float(non_null.max()),
            "mean": float(non_null.mean()),
            "median": float(non_null.median()),
            "std": float(non_null.std()) if len(non_null) > 1 else 0.0,
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "range": float(non_null.max() - non_null.min()),
            "outlier_count": outliers,
            "outlier_pct": round(outliers / len(non_null) * 100.0, 2),
            "extreme_outlier_count": extreme_outliers,
            "extreme_outlier_pct": round(extreme_outliers / len(non_null) * 100.0, 2),
        }

    def _categorical_summary(self, non_null: pd.Series, total: int) -> Dict[str, Any]:
        if non_null.empty:
            return {}
        as_str = non_null.astype(str)
        vc = as_str.value_counts(dropna=True)
        rare_values = vc[vc / max(len(as_str), 1) < 0.01].head(25).to_dict()
        return {
            "most_frequent": vc.index[0] if not vc.empty else None,
            "most_frequent_count": int(vc.iloc[0]) if not vc.empty else 0,
            "top_10_values": vc.head(10).to_dict(),
            "rare_values": rare_values,
            "likely_identifier_like": bool(total > 0 and (non_null.nunique() / total) > 0.95),
        }

    def _datetime_summary(self, non_null: pd.Series) -> Dict[str, Any]:
        if non_null.empty:
            return {}
        return {
            "min_date": str(non_null.min()),
            "max_date": str(non_null.max()),
            "date_range_days": int((non_null.max() - non_null.min()).days) if len(non_null) > 1 else 0,
        }
