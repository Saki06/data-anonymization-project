from pathlib import Path
from typing import Dict, Any, List, Optional

import json
import numpy as np
import pandas as pd
import joblib
import shap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from ...utils.logger import get_logger
except Exception:
    import logging

    def get_logger(name: str):
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger("agent6.shap_explainer")


class SHAPExplainer:
    """
    Agent 6: SHAP explanation

    Responsibilities:
    - load trained model and pair dataset
    - use the same cleaned numeric feature set logic as Agent 4
    - compute SHAP values
    - save global importance + local explanations + summary plot
    """

    def __init__(
        self,
        model_path: Path | str,
        pairs_path: Path | str,
        output_dir: Path | str,
        anon_id_col: str = "anon_index",
        orig_id_col: str = "aux_index",
        sample_size: int = 500,
        drop_meta_cols: Optional[List[str]] = None,
    ):
        self.model_path = Path(model_path)
        self.pairs_path = Path(pairs_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.anon_id_col = anon_id_col
        self.orig_id_col = orig_id_col
        self.sample_size = sample_size

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
        self.X = None
        self.feature_names: List[str] = []
        self.meta_df = None

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def run(self) -> Dict[str, Any]:
        logger.info("Agent 6: SHAP explanation started")

        self._load_model()
        self._load_data()

        shap_values = self._compute_shap_values()
        global_df = self._build_global_importance(shap_values)
        local_df = self._build_local_explanations(shap_values)

        self._save_outputs(global_df, local_df, shap_values)

        logger.info("Agent 6: SHAP explanation complete")

        return {
            "global_csv_path": str(self.output_dir / "shap_global_feature_importance.csv"),
            "global_json_path": str(self.output_dir / "shap_global_feature_importance.json"),
            "local_csv_path": str(self.output_dir / "shap_local_explanations.csv"),
            "summary_plot_path": str(self.output_dir / "shap_global_summary.png"),
        }

    # ------------------------------------------------------------------ #
    # Load helpers
    # ------------------------------------------------------------------ #

    def _load_model(self) -> None:
        logger.info("Loading model from: %s", self.model_path)
        self.model = joblib.load(self.model_path)

    def _load_data(self) -> None:
        logger.info("Loading pair data from: %s", self.pairs_path)
        df = pd.read_csv(self.pairs_path)
        logger.info("   Loaded %s rows × %s columns", df.shape[0], df.shape[1])

        drop_cols_normalized = {str(c).strip().lower() for c in (self.base_meta_cols + self.extra_meta_cols)}

        feature_cols = [
            c for c in df.columns
            if str(c).strip().lower() not in drop_cols_normalized
            and np.issubdtype(df[c].dtype, np.number)
        ]

        if not feature_cols:
            raise ValueError("No numeric feature columns available for SHAP explanation.")

        self.feature_names = feature_cols
        self.X = df[self.feature_names].replace([np.inf, -np.inf], np.nan).fillna(0.0)

        meta_cols = [c for c in df.columns if c not in self.feature_names]
        self.meta_df = df[meta_cols].copy()

        if len(self.X) > self.sample_size:
            sampled_idx = self.X.sample(n=self.sample_size, random_state=42).index
            self.X = self.X.loc[sampled_idx].reset_index(drop=True)
            self.meta_df = self.meta_df.loc[sampled_idx].reset_index(drop=True)
            logger.info("   Sampled %d rows for SHAP computation", self.sample_size)
        else:
            self.X = self.X.reset_index(drop=True)
            self.meta_df = self.meta_df.reset_index(drop=True)

        logger.info("   Using %d feature columns for SHAP", len(self.feature_names))

    # ------------------------------------------------------------------ #
    # SHAP computation
    # ------------------------------------------------------------------ #

    def _unwrap_model_for_shap(self):
        model = self.model

        # Pipeline -> final estimator
        if hasattr(model, "named_steps"):
            try:
                model = list(model.named_steps.values())[-1]
            except Exception:
                pass

        # CalibratedClassifierCV -> underlying estimator
        if hasattr(model, "estimator"):
            try:
                model = model.estimator
            except Exception:
                pass

        # Some sklearn wrappers keep base estimator in base_estimator
        if hasattr(model, "base_estimator"):
            try:
                model = model.base_estimator
            except Exception:
                pass

        return model

    def _predict_fn(self, X_array: np.ndarray) -> np.ndarray:
        if hasattr(self.model, "predict_proba"):
            return self.model.predict_proba(X_array)[:, 1]
        if hasattr(self.model, "decision_function"):
            raw = self.model.decision_function(X_array)
            return (raw - raw.min()) / (raw.max() - raw.min() + 1e-8)
        return self.model.predict(X_array).astype(float)

    def _normalize_shap_values(self, shap_values) -> np.ndarray:
        """
        Return a stable 2D SHAP matrix of shape (n_samples, n_features).

        Different explainers/models may return:
        - list of arrays (legacy multi-output format)
        - 2D ndarray
        - 3D ndarray with an output/class axis
        """
        if isinstance(shap_values, list):
            shap_values = shap_values[-1]

        arr = np.array(shap_values)

        if arr.ndim == 3:
            n_features = len(self.feature_names)

            # Common layouts:
            # (n_samples, n_features, n_outputs)
            # (n_samples, n_outputs, n_features)
            if arr.shape[1] == n_features:
                arr = arr[:, :, -1]
            elif arr.shape[2] == n_features:
                arr = arr[:, -1, :]
            else:
                raise ValueError(
                    f"Unsupported SHAP tensor shape {arr.shape}; "
                    f"could not align with {n_features} features."
                )

        arr = np.squeeze(arr)

        if arr.ndim != 2:
            raise ValueError(
                f"Expected 2D SHAP values after normalization, got shape {arr.shape}."
            )

        return arr

    def _compute_shap_values(self):
        logger.info("Computing SHAP values...")

        model_for_shap = self._unwrap_model_for_shap()

        try:
            explainer = shap.TreeExplainer(model_for_shap)
            shap_values = explainer.shap_values(self.X)

            shap_values = self._normalize_shap_values(shap_values)

            logger.info("   Used TreeExplainer")
            return shap_values

        except Exception as exc:
            logger.warning("TreeExplainer failed: %s", exc)
            logger.info("Falling back to KernelExplainer...")

            background = shap.sample(self.X, min(100, len(self.X)), random_state=42)
            explainer = shap.KernelExplainer(self._predict_fn, background)
            shap_values = explainer.shap_values(self.X, nsamples=min(100, len(self.X) * 2))

            shap_values = self._normalize_shap_values(shap_values)

            logger.info("   Used KernelExplainer")
            return shap_values

    # ------------------------------------------------------------------ #
    # Output builders
    # ------------------------------------------------------------------ #

    def _build_global_importance(self, shap_values: np.ndarray) -> pd.DataFrame:
        mean_abs = np.abs(shap_values).mean(axis=0)

        global_df = pd.DataFrame({
            "feature": self.feature_names,
            "mean_abs_shap": mean_abs,
        }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

        return global_df

    def _build_local_explanations(self, shap_values: np.ndarray) -> pd.DataFrame:
        local_df = self.meta_df.copy()

        if self.anon_id_col not in local_df.columns:
            local_df[self.anon_id_col] = np.arange(len(local_df))

        if self.orig_id_col not in local_df.columns:
            local_df[self.orig_id_col] = np.arange(len(local_df))

        top_feature_idx = np.argmax(np.abs(shap_values), axis=1)
        top_feature_names = [self.feature_names[i] for i in top_feature_idx]
        top_feature_values = [float(shap_values[row_idx, feat_idx]) for row_idx, feat_idx in enumerate(top_feature_idx)]

        local_df["top_feature"] = top_feature_names
        local_df["top_feature_shap_value"] = top_feature_values

        for i, feature in enumerate(self.feature_names):
            local_df[f"shap__{feature}"] = shap_values[:, i]

        return local_df

    # ------------------------------------------------------------------ #
    # Save outputs
    # ------------------------------------------------------------------ #

    def _save_outputs(
        self,
        global_df: pd.DataFrame,
        local_df: pd.DataFrame,
        shap_values: np.ndarray,
    ) -> None:
        global_csv = self.output_dir / "shap_global_feature_importance.csv"
        global_json = self.output_dir / "shap_global_feature_importance.json"
        local_csv = self.output_dir / "shap_local_explanations.csv"
        summary_plot = self.output_dir / "shap_global_summary.png"

        global_df.to_csv(global_csv, index=False)
        local_df.to_csv(local_csv, index=False)

        with open(global_json, "w", encoding="utf-8") as f:
            json.dump(global_df.to_dict(orient="records"), f, indent=2)

        try:
            plt.figure()
            shap.summary_plot(shap_values, self.X, feature_names=self.feature_names, show=False)
            plt.tight_layout()
            plt.savefig(summary_plot, dpi=200, bbox_inches="tight")
            plt.close()
            logger.info("Saved SHAP summary plot to: %s", summary_plot)
        except Exception as exc:
            logger.warning("Could not save SHAP summary plot: %s", exc)

        logger.info("Saved global SHAP CSV to: %s", global_csv)
        logger.info("Saved global SHAP JSON to: %s", global_json)
        logger.info("Saved local SHAP CSV to: %s", local_csv)



# Backwards-compatible name used by existing dashboard wrappers.
AttackModelExplainer = SHAPExplainer