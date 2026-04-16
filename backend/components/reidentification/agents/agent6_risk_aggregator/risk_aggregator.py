from pathlib import Path
from typing import Dict, Any, Optional, List

import json
import numpy as np
import pandas as pd

try:
    from ...utils.logger import get_logger
except Exception:
    import logging

    def get_logger(name: str):
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger("agent6.risk_aggregator")


class RiskAggregator:
    """
    Agent 6: Final risk aggregation

    Combines:
    - ML-based record risk
    - internal/statistical risk
    - uniqueness-related signal
    - optional SHAP feature importance
    - optional pair-level feature correlation

    Outputs:
    - final per-record risk file
    - per-column risk summary
    - global summary JSON
    """

    def __init__(
        self,
        ml_risk_path: Path | str,
        internal_risk_path: Optional[Path | str],
        shap_global_path: Optional[Path | str],
        pair_data_path: Optional[Path | str],
        output_dir: Path | str,
        anon_id_col: str = "anon_index",
    ):
        self.ml_risk_path = Path(ml_risk_path)
        self.internal_risk_path = Path(internal_risk_path) if internal_risk_path else None
        self.shap_global_path = Path(shap_global_path) if shap_global_path else None
        self.pair_data_path = Path(pair_data_path) if pair_data_path else None
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.anon_id_col = anon_id_col

        self.final_df: Optional[pd.DataFrame] = None
        self.column_risk_df: Optional[pd.DataFrame] = None
        self.global_summary: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def run(self) -> Dict[str, Any]:
        logger.info("Agent 6: Risk aggregation started")

        ml_df = self._load_ml_risk()
        internal_df = self._load_internal_risk()
        shap_df = self._load_shap_global()
        pair_df = self._load_pair_data()

        final_df = self._merge_record_level_risks(ml_df, internal_df)
        final_df = self._compute_final_risk_score(final_df)

        column_risk_df = self._build_column_risk_summary(shap_df, pair_df, final_df)
        global_summary = self._build_global_summary(final_df, column_risk_df)

        self.final_df = final_df
        self.column_risk_df = column_risk_df
        self.global_summary = global_summary

        self._save_outputs()

        logger.info("Agent 6: Risk aggregation complete")
        logger.info("   Final records: %s", len(final_df))
        logger.info("   Column summary rows: %s", len(column_risk_df))

        return {
            "final_record_risk_path": str(self.output_dir / "final_record_risk.csv"),
            "column_risk_summary_path": str(self.output_dir / "column_risk_summary.csv"),
            "global_summary_path": str(self.output_dir / "global_risk_summary.json"),
            "global_summary": global_summary,
        }

    # ------------------------------------------------------------------ #
    # Load helpers
    # ------------------------------------------------------------------ #

    def _load_ml_risk(self) -> pd.DataFrame:
        logger.info("Loading ML risk from: %s", self.ml_risk_path)
        df = pd.read_csv(self.ml_risk_path)

        if self.anon_id_col not in df.columns:
            raise ValueError(f"ML risk file must contain '{self.anon_id_col}'")

        if "max_attack_score" not in df.columns:
            raise ValueError("ML risk file must contain 'max_attack_score'")

        return df.copy()

    def _load_internal_risk(self) -> Optional[pd.DataFrame]:
        if not self.internal_risk_path or not self.internal_risk_path.exists():
            logger.info("No internal risk file provided")
            return None

        logger.info("Loading internal risk from: %s", self.internal_risk_path)
        df = pd.read_csv(self.internal_risk_path)

        if self.anon_id_col not in df.columns:
            if "anon_id" in df.columns:
                df = df.rename(columns={"anon_id": self.anon_id_col})
            else:
                logger.warning(
                    "Internal risk file missing '%s'; internal risk merge may be skipped.",
                    self.anon_id_col,
                )

        return df.copy()

    def _load_shap_global(self) -> Optional[pd.DataFrame]:
        if not self.shap_global_path or not self.shap_global_path.exists():
            logger.info("No SHAP global importance file provided")
            return None

        logger.info("Loading SHAP global importance from: %s", self.shap_global_path)
        df = pd.read_csv(self.shap_global_path)
        return df.copy()

    def _load_pair_data(self) -> Optional[pd.DataFrame]:
        if not self.pair_data_path or not self.pair_data_path.exists():
            logger.info("No pair data file provided")
            return None

        logger.info("Loading pair data from: %s", self.pair_data_path)
        df = pd.read_csv(self.pair_data_path)
        return df.copy()

    # ------------------------------------------------------------------ #
    # Record-level merge
    # ------------------------------------------------------------------ #

    def _merge_record_level_risks(
        self,
        ml_df: pd.DataFrame,
        internal_df: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        logger.info("Merging record-level risks...")

        final_df = ml_df.copy()

        if internal_df is not None and self.anon_id_col in internal_df.columns:
            final_df = final_df.merge(
                internal_df,
                on=self.anon_id_col,
                how="left",
                suffixes=("", "_internal"),
            )
            logger.info("   Internal risk merged successfully")
        else:
            logger.info("   Internal risk not merged")

        return final_df

    # ------------------------------------------------------------------ #
    # Final risk score logic
    # ------------------------------------------------------------------ #

    def _compute_final_risk_score(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Computing final weighted risk score...")

        out = df.copy()

        # ML risk
        ml_score = self._safe_normalize(out["max_attack_score"]) if "max_attack_score" in out.columns else 0.0

        # Internal risk
        internal_score = self._resolve_internal_risk_score(out)

        # Uniqueness / k-size risk
        uniqueness_score = self._resolve_uniqueness_score(out)

        w_ml = 0.5
        w_internal = 0.3
        w_uniqueness = 0.2

        out["ml_risk_component"] = ml_score
        out["internal_risk_component"] = internal_score
        out["uniqueness_risk_component"] = uniqueness_score

        out["final_risk_score"] = (
            w_ml * out["ml_risk_component"]
            + w_internal * out["internal_risk_component"]
            + w_uniqueness * out["uniqueness_risk_component"]
        ) * 100.0

        out["final_risk_level"] = out["final_risk_score"].apply(self._map_final_risk_level)

        logger.info("   Final risk score computed")

        return out

    def _resolve_internal_risk_score(self, df: pd.DataFrame) -> pd.Series:
        """
        Prefer explicit internal risk score columns if available.
        """
        candidate_cols = [
            "combined_internal_risk",
            "internal_risk_score",
            "risk_score_internal",
            "lof_risk_score",
            "anomaly_score",
        ]

        for col in candidate_cols:
            if col in df.columns:
                logger.info("   Using internal risk source column: %s", col)
                return self._safe_normalize(df[col])

        logger.info("   No explicit internal risk score found; using zeros")
        return pd.Series(np.zeros(len(df)), index=df.index, dtype=float)

    def _resolve_uniqueness_score(self, df: pd.DataFrame) -> pd.Series:
        """
        Handles direction correctly:
        - uniqueness_score / unique_score / uniqueness -> higher means riskier
        - k_size / k_anonymity -> higher means safer, so invert after normalization
        """
        direct_risk_cols = [
            "uniqueness_score",
            "unique_score",
            "uniqueness",
            "pct_unique",
            "is_unique",
        ]
        inverse_risk_cols = [
            "k_size",
            "k_anonymity",
        ]

        for col in direct_risk_cols:
            if col in df.columns:
                logger.info("   Using direct uniqueness-risk column: %s", col)
                return self._safe_normalize(df[col])

        for col in inverse_risk_cols:
            if col in df.columns:
                logger.info("   Using inverse uniqueness-risk column: %s", col)
                norm = self._safe_normalize(df[col])
                return 1.0 - norm

        logger.info("   No uniqueness-related column found; using zeros")
        return pd.Series(np.zeros(len(df)), index=df.index, dtype=float)

    @staticmethod
    def _safe_normalize(series: pd.Series) -> pd.Series:
        vals = pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)

        min_val = vals.min()
        max_val = vals.max()

        if pd.isna(min_val) or pd.isna(max_val) or max_val == min_val:
            return pd.Series(np.zeros(len(vals)), index=vals.index, dtype=float)

        return (vals - min_val) / (max_val - min_val)

    @staticmethod
    def _map_final_risk_level(score: float) -> str:
        if score < 20:
            return "low"
        if score < 40:
            return "moderate"
        if score < 60:
            return "high"
        if score < 80:
            return "very_high"
        return "critical"

    # ------------------------------------------------------------------ #
    # Column-level summary
    # ------------------------------------------------------------------ #

    def _build_column_risk_summary(
        self,
        shap_df: Optional[pd.DataFrame],
        pair_df: Optional[pd.DataFrame],
        final_df: pd.DataFrame,
    ) -> pd.DataFrame:
        logger.info("Building column-level risk summary...")

        rows: List[Dict[str, Any]] = []

        # SHAP contribution
        if shap_df is not None and not shap_df.empty:
            shap_feature_col = None
            shap_value_col = None

            for c in ["feature", "column"]:
                if c in shap_df.columns:
                    shap_feature_col = c
                    break

            for c in ["mean_abs_shap", "importance", "shap_importance"]:
                if c in shap_df.columns:
                    shap_value_col = c
                    break

            if shap_feature_col and shap_value_col:
                for _, row in shap_df.iterrows():
                    rows.append(
                        {
                            "column": row[shap_feature_col],
                            "shap_importance": float(row[shap_value_col]),
                            "pair_risk_correlation": np.nan,
                        }
                    )

        summary_df = pd.DataFrame(rows)

        # Pair feature correlation with final record risk
        if pair_df is not None and not pair_df.empty and self.anon_id_col in pair_df.columns:
            logger.info("   Computing pair-feature correlations with final risk...")

            merged = pair_df.merge(
                final_df[[self.anon_id_col, "final_risk_score"]],
                on=self.anon_id_col,
                how="left",
            )

            feature_cols = [
                c for c in merged.columns
                if pd.api.types.is_numeric_dtype(merged[c])
                and c not in {
                    "final_risk_score",
                    "label",
                    "aux_index",
                    "anon_index",
                    "pair_index",
                    "orig_id",
                    "anon_id",
                    "aux_id",
                    "id",
                    "ids",
                }
            ]

            correlations = []
            for col in feature_cols:
                try:
                    corr = merged[col].corr(merged["final_risk_score"])
                    correlations.append(
                        {
                            "column": col,
                            "pair_risk_correlation": float(corr) if pd.notna(corr) else np.nan,
                        }
                    )
                except Exception:
                    correlations.append(
                        {
                            "column": col,
                            "pair_risk_correlation": np.nan,
                        }
                    )

            corr_df = pd.DataFrame(correlations)

            if summary_df.empty:
                summary_df = corr_df
            else:
                summary_df = summary_df.merge(corr_df, on="column", how="outer", suffixes=("", "_new"))
                if "pair_risk_correlation_new" in summary_df.columns:
                    summary_df["pair_risk_correlation"] = summary_df["pair_risk_correlation"].combine_first(
                        summary_df["pair_risk_correlation_new"]
                    )
                    summary_df = summary_df.drop(columns=["pair_risk_correlation_new"])

        if summary_df.empty:
            summary_df = pd.DataFrame(columns=["column", "shap_importance", "pair_risk_correlation"])

        if "shap_importance" not in summary_df.columns:
            summary_df["shap_importance"] = np.nan
        if "pair_risk_correlation" not in summary_df.columns:
            summary_df["pair_risk_correlation"] = np.nan

        summary_df["shap_importance_norm"] = self._safe_normalize(
            pd.to_numeric(summary_df["shap_importance"], errors="coerce").fillna(0.0)
        )
        summary_df["pair_corr_abs_norm"] = self._safe_normalize(
            pd.to_numeric(summary_df["pair_risk_correlation"], errors="coerce").fillna(0.0).abs()
        )

        summary_df["column_risk_score"] = (
            0.7 * summary_df["shap_importance_norm"]
            + 0.3 * summary_df["pair_corr_abs_norm"]
        ) * 100.0

        summary_df = summary_df.sort_values("column_risk_score", ascending=False).reset_index(drop=True)

        return summary_df

    # ------------------------------------------------------------------ #
    # Global summary
    # ------------------------------------------------------------------ #

    def _build_global_summary(
        self,
        final_df: pd.DataFrame,
        column_risk_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        logger.info("Building global summary...")

        total = len(final_df)

        counts = final_df["final_risk_level"].value_counts().to_dict()

        global_summary = {
            "total_records": int(total),
            "risk_level_counts": counts,
            "risk_level_percentages": {
                level: round((count / total) * 100, 2) if total else 0.0
                for level, count in counts.items()
            },
            "final_risk_score_summary": {
                "mean": float(final_df["final_risk_score"].mean()) if total else 0.0,
                "median": float(final_df["final_risk_score"].median()) if total else 0.0,
                "min": float(final_df["final_risk_score"].min()) if total else 0.0,
                "max": float(final_df["final_risk_score"].max()) if total else 0.0,
            },
            "top_risky_columns": column_risk_df.head(10).to_dict(orient="records"),
        }

        return global_summary

    # ------------------------------------------------------------------ #
    # Save outputs
    # ------------------------------------------------------------------ #

    def _save_outputs(self) -> None:
        if self.final_df is None or self.column_risk_df is None or self.global_summary is None:
            raise ValueError("No outputs available to save. Run aggregation first.")

        final_path = self.output_dir / "final_record_risk.csv"
        column_path = self.output_dir / "column_risk_summary.csv"
        global_path = self.output_dir / "global_risk_summary.json"

        self.final_df.to_csv(final_path, index=False)
        self.column_risk_df.to_csv(column_path, index=False)

        with open(global_path, "w", encoding="utf-8") as f:
            json.dump(self.global_summary, f, indent=2)

        logger.info("Saved final record risk to: %s", final_path)
        logger.info("Saved column risk summary to: %s", column_path)
        logger.info("Saved global risk summary to: %s", global_path)