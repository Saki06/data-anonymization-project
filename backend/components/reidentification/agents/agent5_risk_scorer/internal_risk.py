import pandas as pd
import numpy as np
import json
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.neighbors import LocalOutlierFactor

from ...utils.logger import get_logger

logger = get_logger("agent6b.internal_risk")


class InternalRiskAnalyzer:

    def __init__(
        self,
        anon_path: Path,
        qi_columns: list,
        output_dir: Path = Path("data/internal_risk"),
        sensitive_column: str = None,
    ):
        self.anon_path = Path(anon_path)
        self.qi_columns = list(qi_columns)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.sensitive_column = sensitive_column

        # runtime flags set by sub-methods
        self.lof_enabled: bool = True
        self.l_diversity_enabled: bool = False

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self):
        logger.info("Agent 6-B: Internal Re-Identification Detector started")

        df = pd.read_csv(self.anon_path)
        logger.info(f"   Loaded anonymized dataset: {df.shape}")

        # Insert anon_id only if missing
        if "anon_id" not in df.columns:
            df.insert(0, "anon_id", range(len(df)))

        # Validate QI columns against actual dataframe
        df = self._validate_qi_columns(df)

        logger.info(f"   QI columns in use: {self.qi_columns}")

        logger.info("Computing equivalence class sizes...")
        df = self._compute_k_anonymity(df)

        logger.info("Computing cluster anomaly scores...")
        df = self._compute_cluster_scores(df)

        logger.info("Computing l-diversity...")
        df = self._compute_l_diversity(df)

        logger.info("Computing combined risk score...")
        df = self._compute_combined_risk(df)

        logger.info("Generating summary...")
        summary = self._generate_summary(df)

        self._save(df, summary)

        logger.info("Agent 6-B completed successfully!")
        return {
            "risk_csv": str(self.output_dir / "internal_risk_per_record.csv"),
            "summary_json": str(self.output_dir / "internal_risk_summary.json"),
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_qi_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in self.qi_columns if c not in df.columns]
        if missing:
            logger.warning(f"   QI columns not found in dataset (dropping): {missing}")
            self.qi_columns = [c for c in self.qi_columns if c in df.columns]

        if not self.qi_columns:
            raise ValueError(
                "No valid QI columns remain after validation. "
                "Check that qi_columns match actual column names in the anonymized dataset."
            )
        return df

    # ------------------------------------------------------------------
    # k-anonymity
    # ------------------------------------------------------------------

    def _compute_k_anonymity(self, df: pd.DataFrame) -> pd.DataFrame:
        group = df.groupby(self.qi_columns)
        k_sizes = group.size().reset_index(name="k_size")
        df = df.merge(k_sizes, on=self.qi_columns, how="left")

        # existing column — preserved
        df["uniqueness_score"] = 1.0 / df["k_size"]

        # new research-friendly columns
        df["k_anonymity"] = df["k_size"]
        df["is_unique"] = (df["k_anonymity"] == 1).astype(int)

        # row-wise missing fraction across QI columns
        df["qi_missing_rate"] = df[self.qi_columns].isnull().mean(axis=1)

        pct_unique = float(df["is_unique"].mean() * 100)
        logger.info(f"   k-anonymity computed. Unique records: {pct_unique:.1f}%")
        logger.info(
            f"   k stats — min: {df['k_size'].min()}, "
            f"median: {df['k_size'].median():.1f}, "
            f"mean: {df['k_size'].mean():.2f}"
        )

        return df

    # ------------------------------------------------------------------
    # LOF cluster anomaly
    # ------------------------------------------------------------------

    def _compute_cluster_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        from sklearn.preprocessing import LabelEncoder

        n_neighbors = min(20, len(df) - 1)

        if n_neighbors < 2:
            logger.warning(
                f"   Dataset too small for LOF (n={len(df)}). "
                "Skipping cluster anomaly scoring — setting cluster_anomaly_score = 0.0."
            )
            df["cluster_anomaly_score"] = 0.0
            self.lof_enabled = False
            return df

        X_encoded = df[self.qi_columns].copy()

        for col in self.qi_columns:
            X_encoded[col] = X_encoded[col].astype(str)
            le = LabelEncoder()
            try:
                X_encoded[col] = le.fit_transform(X_encoded[col])
            except Exception as e:
                logger.warning(f"   Could not encode column '{col}': {e}. Filling with 0.")
                X_encoded[col] = 0

        X = X_encoded.astype(float)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        pca = PCA(n_components=min(10, len(self.qi_columns)))
        X_pca = pca.fit_transform(X_scaled)

        lof = LocalOutlierFactor(
            n_neighbors=n_neighbors,
            contamination=0.02,
            novelty=False,
        )
        lof.fit_predict(X_pca)
        anomaly_scores = -lof.negative_outlier_factor_

        df["cluster_anomaly_score"] = self._normalize(anomaly_scores)
        self.lof_enabled = True
        logger.info(f"   LOF cluster anomaly computed (n_neighbors={n_neighbors}).")

        return df

    # ------------------------------------------------------------------
    # l-diversity (optional)
    # ------------------------------------------------------------------

    def _compute_l_diversity(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.sensitive_column:
            df["l_diversity"] = np.nan
            self.l_diversity_enabled = False
            logger.info("   l-diversity skipped (no sensitive_column provided).")
            return df

        if self.sensitive_column not in df.columns:
            logger.warning(
                f"   sensitive_column '{self.sensitive_column}' not found in dataset. "
                "Skipping l-diversity."
            )
            df["l_diversity"] = np.nan
            self.l_diversity_enabled = False
            return df

        l_vals = (
            df.groupby(self.qi_columns)[self.sensitive_column]
            .transform("nunique")
        )
        df["l_diversity"] = l_vals
        self.l_diversity_enabled = True
        logger.info(
            f"   l-diversity computed on '{self.sensitive_column}'. "
            f"min={df['l_diversity'].min():.0f}, "
            f"median={df['l_diversity'].median():.1f}, "
            f"mean={df['l_diversity'].mean():.2f}"
        )

        return df

    # ------------------------------------------------------------------
    # Combined risk + dynamic thresholds
    # ------------------------------------------------------------------

    def _compute_combined_risk(self, df: pd.DataFrame) -> pd.DataFrame:
        df["combined_risk"] = (
            0.6 * df["uniqueness_score"] +
            0.4 * df["cluster_anomaly_score"]
        )

        logger.info("   Calculating dynamic risk thresholds based on internal risk distribution...")
        all_scores = df["combined_risk"].values

        percentile_95 = float(np.percentile(all_scores, 95))
        percentile_80 = float(np.percentile(all_scores, 80))
        percentile_50 = float(np.percentile(all_scores, 50))

        logger.info(f"   CRITICAL >= {percentile_95:.4f} | HIGH >= {percentile_80:.4f} | MEDIUM >= {percentile_50:.4f}")

        def assign_risk(score):
            if score >= percentile_95:
                return "critical"
            elif score >= percentile_80:
                return "high"
            elif score >= percentile_50:
                return "medium"
            else:
                return "low"

        df["risk_level"] = df["combined_risk"].apply(assign_risk)

        self.dynamic_thresholds = {
            "critical_threshold": percentile_95,
            "high_threshold": percentile_80,
            "medium_threshold": percentile_50,
            "percentile_95": percentile_95,
            "percentile_80": percentile_80,
            "percentile_50": percentile_50,
        }

        return df

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize(self, arr):
        arr = np.array(arr)
        return (arr - arr.min()) / (arr.max() - arr.min() + 1e-9)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _generate_summary(self, df: pd.DataFrame) -> dict:
        total = len(df)
        critical = int((df["risk_level"] == "critical").sum())
        high = int((df["risk_level"] == "high").sum())
        med = int((df["risk_level"] == "medium").sum())
        low = int((df["risk_level"] == "low").sum())

        pct_unique = float(df["is_unique"].mean() * 100)
        suppression_rate = float(df["qi_missing_rate"].mean())

        summary = {
            # existing keys — preserved
            "total_records": total,
            "critical_risk": critical,
            "high_risk": high,
            "medium_risk": med,
            "low_risk": low,
            "dynamic_thresholds": self.dynamic_thresholds if hasattr(self, "dynamic_thresholds") else {},
            "percent_high": float(high / total * 100) if total else 0.0,
            "percent_medium": float(med / total * 100) if total else 0.0,
            "percent_low": float(low / total * 100) if total else 0.0,
            # new research fields
            "pct_unique": round(pct_unique, 4),
            "k_min": int(df["k_size"].min()),
            "k_median": float(df["k_size"].median()),
            "k_mean": round(float(df["k_size"].mean()), 4),
            "qi_columns_used": self.qi_columns,
            "suppression_rate_overall": round(suppression_rate, 6),
            "lof_enabled": self.lof_enabled,
            "l_diversity_enabled": self.l_diversity_enabled,
        }

        if self.l_diversity_enabled:
            summary["l_min"] = int(df["l_diversity"].min())
            summary["l_median"] = float(df["l_diversity"].median())
            summary["l_mean"] = round(float(df["l_diversity"].mean()), 4)

        logger.info(
            f"   Summary — total={total}, pct_unique={pct_unique:.1f}%, "
            f"k_min={summary['k_min']}, k_mean={summary['k_mean']:.2f}, "
            f"suppression_rate={suppression_rate:.4f}, "
            f"lof_enabled={self.lof_enabled}, l_diversity_enabled={self.l_diversity_enabled}"
        )

        return summary

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self, df: pd.DataFrame, summary: dict):
        csv_path = self.output_dir / "internal_risk_per_record.csv"
        json_path = self.output_dir / "internal_risk_summary.json"

        df.to_csv(csv_path, index=False)
        with open(json_path, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"   Saved internal risk CSV:  {csv_path}")
        logger.info(f"   Saved internal risk JSON: {json_path}")
