from pathlib import Path
from typing import Dict, Any, List, Optional

import json
import numpy as np
import pandas as pd
import joblib

try:
    from ...utils.logger import get_logger
except Exception:
    import logging

    def get_logger(name: str):
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger("agent5.risk_scorer")


class RiskScorer:
    """
    Agent 5: Risk scoring

    Responsibilities:
    - load pair-level features and trained model
    - score each pair with attack probability
    - aggregate to anonymized-record level
    - assign dynamic percentile-based risk levels
    - save scored outputs and summary
    """

    def __init__(
        self,
        pairs_path: Path | str,
        model_path: Path | str,
        output_dir: Path | str,
        anon_id_col: str = "anon_index",
        orig_id_col: str = "aux_index",
        drop_meta_cols: Optional[List[str]] = None,
        high_risk_threshold: float = 0.75,
        medium_risk_threshold: float = 0.40,
    ):
        self.pairs_path = Path(pairs_path)
        self.model_path = Path(model_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.anon_id_col = anon_id_col
        self.orig_id_col = orig_id_col

        self.high_thr = high_risk_threshold
        self.med_thr = medium_risk_threshold

        self.base_meta_cols = [
            "label",
            anon_id_col,
            orig_id_col,
            "pair_index",
            "aux_index",
            "anon_index",
            "orig_id",
            "anon_id",
            "aux_id",
            "id",
            "ids",
            "pair_id",
            "true_match",
            "match_label",
            "y",
            "similarity_score",
        ]
        self.extra_meta_cols = drop_meta_cols or []

        self.model = None
        self.feature_cols: List[str] = []
        self.dynamic_thresholds: Dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def run(self) -> Dict[str, Any]:
        logger.info("Agent 5: Risk scoring started")

        self._load_model()
        pairs_df = self._load_pairs()

        pairs_df = self._score_pairs(pairs_df)
        record_df = self._aggregate_by_record(pairs_df)
        summary = self._summarize_risk(record_df)

        self._save_outputs(pairs_df, record_df, summary)

        logger.info("Agent 5: Risk scoring complete")
        logger.info("   Critical risk records: %s", summary["counts"]["critical"])
        logger.info("   High risk records:     %s", summary["counts"]["high"])
        logger.info("   Medium risk records:   %s", summary["counts"]["medium"])
        logger.info("   Low risk records:      %s", summary["counts"]["low"])

        return {
            "pairs_scored_path": str(self.output_dir / "risk_pairs_with_scores.csv"),
            "record_risk_path": str(self.output_dir / "risk_per_record.csv"),
            "summary_path": str(self.output_dir / "risk_summary.json"),
            "summary": summary,
        }

    # ------------------------------------------------------------------ #
    # Load helpers
    # ------------------------------------------------------------------ #

    def _load_model(self) -> None:
        logger.info("Loading ML attacker model from: %s", self.model_path)
        self.model = joblib.load(self.model_path)

    def _load_pairs(self) -> pd.DataFrame:
        logger.info("Loading pair dataset from: %s", self.pairs_path)
        df = pd.read_csv(self.pairs_path)
        logger.info("   Loaded %s rows × %s columns", df.shape[0], df.shape[1])

        if self.anon_id_col not in df.columns:
            raise ValueError(f"Column '{self.anon_id_col}' not found in pairs CSV")

        if self.orig_id_col not in df.columns:
            logger.warning(
                "Column '%s' not found. Continuing without original-side grouping.",
                self.orig_id_col,
            )

        # Only keep positive pairs (label=1) for risk scoring.
        # Negative pairs are synthetic non-matches used only for ML training
        # and should NOT be counted as matched/re-identified records.
        if "label" in df.columns:
            total_before = len(df)
            df = df[df["label"] == 1].copy()
            logger.info(
                "   Filtered to positive pairs only: %d → %d rows (dropped %d negative pairs)",
                total_before, len(df), total_before - len(df),
            )
            if df.empty:
                raise ValueError("No positive pairs (label=1) found in pairs CSV. Cannot score risk.")

        return df

    # ------------------------------------------------------------------ #
    # Feature selection
    # ------------------------------------------------------------------ #

    def _get_feature_columns(self, df: pd.DataFrame) -> List[str]:
        drop_cols_normalized = {str(c).strip().lower() for c in (self.base_meta_cols + self.extra_meta_cols)}

        feature_cols = [
            c for c in df.columns
            if str(c).strip().lower() not in drop_cols_normalized
            and np.issubdtype(df[c].dtype, np.number)
        ]

        if not feature_cols:
            raise ValueError("No numeric feature columns found for risk scoring.")

        logger.info("   Using %d feature columns for scoring.", len(feature_cols))
        logger.info(
            "   Feature list: %s",
            feature_cols[:10] + (["..."] if len(feature_cols) > 10 else []),
        )
        return feature_cols

    # ------------------------------------------------------------------ #
    # Pair scoring
    # ------------------------------------------------------------------ #

    def _score_pairs(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Computing attack probabilities for each pair...")

        self.feature_cols = self._get_feature_columns(df)
        X = df[self.feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).values

        if hasattr(self.model, "predict_proba"):
            scores = self.model.predict_proba(X)[:, 1]
        elif hasattr(self.model, "decision_function"):
            raw = self.model.decision_function(X)
            scores = (raw - raw.min()) / (raw.max() - raw.min() + 1e-8)
        else:
            logger.warning(
                "Model has no predict_proba/decision_function. Using binary predictions as scores."
            )
            scores = self.model.predict(X).astype(float)

        scored = df.copy()
        scored["attack_score"] = scores

        logger.info("   Example scores:")
        logger.info(scored[["attack_score"]].head().to_string(index=False))

        return scored

    # ------------------------------------------------------------------ #
    # Record aggregation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _assign_risk_level(score: float, critical_thr: float, high_thr: float, med_thr: float) -> str:
        if score >= critical_thr:
            return "critical"
        if score >= high_thr:
            return "high"
        if score >= med_thr:
            return "medium"
        return "low"

    def _aggregate_by_record(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Aggregating scores at anonymized-record level...")

        group = df.groupby(self.anon_id_col)["attack_score"]

        record_df = group.agg(
            max_attack_score="max",
            mean_attack_score="mean",
            pair_count="count",
        ).reset_index()

        logger.info("Calculating dynamic risk thresholds based on score distribution...")
        all_scores = record_df["max_attack_score"].values

        percentile_95 = float(np.percentile(all_scores, 95))
        percentile_80 = float(np.percentile(all_scores, 80))
        percentile_50 = float(np.percentile(all_scores, 50))

        self.dynamic_thresholds = {
            "critical_threshold": percentile_95,
            "high_threshold": percentile_80,
            "medium_threshold": percentile_50,
            "percentile_95": percentile_95,
            "percentile_80": percentile_80,
            "percentile_50": percentile_50,
        }

        logger.info("   CRITICAL >= %.4f", percentile_95)
        logger.info("   HIGH     >= %.4f and < %.4f", percentile_80, percentile_95)
        logger.info("   MEDIUM   >= %.4f and < %.4f", percentile_50, percentile_80)
        logger.info("   LOW      < %.4f", percentile_50)

        record_df["risk_level"] = record_df["max_attack_score"].apply(
            lambda score: self._assign_risk_level(score, percentile_95, percentile_80, percentile_50)
        )

        logger.info("   Sample record-level risk:")
        logger.info(record_df.head().to_string(index=False))

        return record_df

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #

    def _summarize_risk(self, record_df: pd.DataFrame) -> Dict[str, Any]:
        logger.info("Creating risk summary statistics...")

        total = len(record_df)
        critical = int((record_df["risk_level"] == "critical").sum())
        high = int((record_df["risk_level"] == "high").sum())
        med = int((record_df["risk_level"] == "medium").sum())
        low = int((record_df["risk_level"] == "low").sum())

        summary = {
            "total_records": int(total),
            "counts": {
                "critical": critical,
                "high": high,
                "medium": med,
                "low": low,
            },
            "percentages": {
                "critical": round((critical / total) * 100, 2) if total else 0.0,
                "high": round((high / total) * 100, 2) if total else 0.0,
                "medium": round((med / total) * 100, 2) if total else 0.0,
                "low": round((low / total) * 100, 2) if total else 0.0,
            },
            "score_summary": {
                "max_score": float(record_df["max_attack_score"].max()) if total else 0.0,
                "min_score": float(record_df["max_attack_score"].min()) if total else 0.0,
                "mean_score": float(record_df["max_attack_score"].mean()) if total else 0.0,
                "median_score": float(record_df["max_attack_score"].median()) if total else 0.0,
            },
            "dynamic_thresholds": self.dynamic_thresholds,
        }

        return summary

    # ------------------------------------------------------------------ #
    # Save outputs
    # ------------------------------------------------------------------ #

    def _save_outputs(
        self,
        pairs_df: pd.DataFrame,
        record_df: pd.DataFrame,
        summary: Dict[str, Any],
    ) -> None:
        pair_path = self.output_dir / "risk_pairs_with_scores.csv"
        record_path = self.output_dir / "risk_per_record.csv"
        summary_path = self.output_dir / "risk_summary.json"

        pairs_df.to_csv(pair_path, index=False)
        record_df.to_csv(record_path, index=False)

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        logger.info("Saved pair-level risk scores to: %s", pair_path)
        logger.info("Saved record-level risk summary to: %s", record_path)
        logger.info("Saved JSON summary to: %s", summary_path)