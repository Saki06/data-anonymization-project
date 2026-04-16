from pathlib import Path
from typing import Dict, Any, List, Tuple

import json
import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
    average_precision_score,
    precision_recall_curve
)
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold
from sklearn.calibration import CalibratedClassifierCV

import joblib

# optional XGBoost
try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

# logger import
try:
    from ...utils.logger import get_logger
except Exception:
    import logging

    def get_logger(name: str):
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger("agent4.ml_attacker")


class MLAttackModel:

    def __init__(
        self,
        train_path: Path,
        test_path: Path,
        output_dir: Path,
        model_names: List[str] = None,
        random_state: int = 42,
    ):
        self.train_path = Path(train_path)
        self.test_path = Path(test_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if model_names is None:
            model_names = ["logreg", "rf", "gbm", "xgb"]

        if "xgb" in model_names and not HAS_XGB:
            logger.warning("XGBoost not installed; skipping 'xgb' model.")
            model_names = [m for m in model_names if m != "xgb"]

        self.model_names = model_names
        self.random_state = random_state

        self.feature_names: List[str] = []
        self.models: Dict[str, Any] = {}
        self.metrics: Dict[str, Any] = {}
        self.best_model_name: str = ""
        self.best_model = None
        self.cv_results: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def run(self) -> Dict[str, Any]:
        logger.info("Agent 4: ML attacker training started")

        train_df, test_df = self._load_data()
        X_train, y_train, X_test, y_test = self._prepare_features(train_df, test_df)

        self._cross_validate_models(X_train, y_train)
        self._train_all_models(X_train, y_train, X_test, y_test)
        self._select_best_model()
        self._calibrate_best_model(X_train, y_train, X_test, y_test)
        self._compute_baseline(test_df, y_test)
        self._save_best_model()
        self._save_reports()

        logger.info("Agent 4: training complete")
        logger.info(f"   Best model: {self.best_model_name}")
        logger.info(
            f"   Best PR-AUC:  {self.metrics[self.best_model_name].get('pr_auc', float('nan')):.4f}"
        )
        logger.info(
            f"   Best ROC-AUC: {self.metrics[self.best_model_name].get('roc_auc', float('nan')):.4f}"
        )
        logger.info(
            f"   Best threshold: {self.metrics[self.best_model_name].get('best_threshold', 0.5):.4f}"
        )

        return {
            "best_model_name": self.best_model_name,
            "best_model_path": str(self.output_dir / "best_attack_model.pkl"),
            "metrics": self.metrics,
            "feature_names": self.feature_names,
        }

    # ------------------------------------------------------------------ #
    # Data loading & preparation
    # ------------------------------------------------------------------ #

    def _load_data(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        logger.info(f"Loading train pairs: {self.train_path}")
        logger.info(f"Loading test pairs:  {self.test_path}")

        train_df = pd.read_csv(self.train_path)
        test_df = pd.read_csv(self.test_path)

        logger.info(f"   Train: {train_df.shape[0]:,} rows × {train_df.shape[1]} cols")
        logger.info(f"   Test:  {test_df.shape[0]:,} rows × {test_df.shape[1]} cols")

        if "label" not in train_df.columns or "label" not in test_df.columns:
            raise ValueError("Both train & test must contain a 'label' column (0/1).")

        return train_df, test_df

    def _prepare_features(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        logger.info("Preparing feature matrices...")

        # IMPORTANT: exclude metadata/index columns from training
        NON_FEATURE_COLS = {
            "label", "match_label", "y", "pair_index",
            "orig_id", "anon_id", "pair_id", "id", "true_match",
            "aux_id", "aux_index", "anon_index", "orig_index",
            "similarity_score", "ids"
        }

        drop_cols = [
            col for col in train_df.columns
            if str(col).strip().lower() in NON_FEATURE_COLS
        ]

        numeric_cols = (
            train_df.drop(columns=drop_cols, errors="ignore")
            .select_dtypes(include=[np.number])
            .columns
        )
        self.feature_names = list(numeric_cols)

        if not self.feature_names:
            raise ValueError("No numeric feature columns found for training.")

        logger.info(f"   Using {len(self.feature_names)} numeric features for training.")
        logger.info(
            f"   Feature list: {self.feature_names[:10]}{'...' if len(self.feature_names) > 10 else ''}"
        )

        pos_rate = float(np.mean(train_df["label"].values))
        logger.info(f"   Train samples: {len(train_df):,}  |  Positive rate: {pos_rate:.3f}")

        train_features = (
            train_df[self.feature_names]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
        )
        X_train = train_features.values
        y_train = train_df["label"].values.astype(int)

        test_features = test_df.reindex(columns=self.feature_names, fill_value=0.0)
        test_features = test_features.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        X_test = test_features.values
        y_test = test_df["label"].values.astype(int)

        self.n_train = int(X_train.shape[0])
        self.n_test = int(X_test.shape[0])

        logger.info(f"   Positive labels in train: {np.sum(y_train == 1):,}")
        logger.info(f"   Negative labels in train: {np.sum(y_train == 0):,}")
        logger.info(f"   Positive labels in test:  {np.sum(y_test == 1):,}")
        logger.info(f"   Negative labels in test:  {np.sum(y_test == 0):,}")

        return X_train, y_train, X_test, y_test

    # ------------------------------------------------------------------ #
    # Model training
    # ------------------------------------------------------------------ #

    def _train_all_models(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray
    ):
        logger.info("Training ML attacker models...")

        for name in self.model_names:
            logger.info(f"\nTraining model: {name}")
            model = self._build_model(name)

            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)

            if hasattr(model, "predict_proba"):
                y_scores = model.predict_proba(X_test)[:, 1]
            elif hasattr(model, "decision_function"):
                scores_raw = model.decision_function(X_test)
                y_scores = (scores_raw - scores_raw.min()) / (scores_raw.max() - scores_raw.min() + 1e-8)
            else:
                y_scores = y_pred.astype(float)

            metrics = self._evaluate_model(y_test, y_pred, y_scores)
            self.metrics[name] = metrics
            self.models[name] = model

            logger.info(
                f"   {name}: PR-AUC={metrics['pr_auc']:.4f}, "
                f"ROC-AUC={metrics['roc_auc']:.4f}, "
                f"F1={metrics['f1']:.4f}"
            )

    def _build_model(self, name: str):
        if name == "logreg":
            return Pipeline([
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=self.random_state
                ))
            ])

        if name == "rf":
            return RandomForestClassifier(
                n_estimators=200,
                max_depth=None,
                min_samples_split=5,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=self.random_state,
                n_jobs=-1
            )

        if name == "gbm":
            return GradientBoostingClassifier(
                n_estimators=150,
                learning_rate=0.05,
                max_depth=3,
                random_state=self.random_state
            )

        if name == "xgb" and HAS_XGB:
            return XGBClassifier(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=5,
                subsample=0.9,
                colsample_bytree=0.9,
                objective="binary:logistic",
                eval_metric="logloss",
                random_state=self.random_state
            )

        raise ValueError(f"Unknown model name: {name}")

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #

    def _evaluate_model(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_scores: np.ndarray
    ) -> Dict[str, Any]:
        precision_curve, recall_curve, thresholds = precision_recall_curve(y_true, y_scores)
        pr_auc = average_precision_score(y_true, y_scores)
        roc_auc = roc_auc_score(y_true, y_scores)

        f1_scores = 2 * (precision_curve[:-1] * recall_curve[:-1]) / (
            precision_curve[:-1] + recall_curve[:-1] + 1e-8
        )

        if len(f1_scores) > 0:
            best_idx = int(np.argmax(f1_scores))
            best_threshold = float(thresholds[best_idx]) if best_idx < len(thresholds) else 0.5
        else:
            best_threshold = 0.5

        y_pred_opt = (y_scores >= best_threshold).astype(int)

        return {
            "accuracy": float(accuracy_score(y_true, y_pred_opt)),
            "precision": float(precision_score(y_true, y_pred_opt, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred_opt, zero_division=0)),
            "f1": float(f1_score(y_true, y_pred_opt, zero_division=0)),
            "roc_auc": float(roc_auc),
            "pr_auc": float(pr_auc),
            "best_threshold": float(best_threshold),
            "confusion_matrix": confusion_matrix(y_true, y_pred_opt).tolist(),
            "classification_report": classification_report(y_true, y_pred_opt, zero_division=0),
        }

    # ------------------------------------------------------------------ #
    # Cross-validation
    # ------------------------------------------------------------------ #

    def _cross_validate_models(self, X_train: np.ndarray, y_train: np.ndarray):
        logger.info("Running cross-validation...")

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=self.random_state)
        self.cv_results = {}

        for name in self.model_names:
            fold_pr_aucs = []
            fold_roc_aucs = []

            for train_idx, val_idx in cv.split(X_train, y_train):
                X_tr, X_val = X_train[train_idx], X_train[val_idx]
                y_tr, y_val = y_train[train_idx], y_train[val_idx]

                model = self._build_model(name)
                model.fit(X_tr, y_tr)

                if hasattr(model, "predict_proba"):
                    y_scores = model.predict_proba(X_val)[:, 1]
                elif hasattr(model, "decision_function"):
                    raw = model.decision_function(X_val)
                    y_scores = (raw - raw.min()) / (raw.max() - raw.min() + 1e-8)
                else:
                    y_scores = model.predict(X_val).astype(float)

                fold_pr_aucs.append(average_precision_score(y_val, y_scores))
                fold_roc_aucs.append(roc_auc_score(y_val, y_scores))

            self.cv_results[name] = {
                "mean_pr_auc": float(np.mean(fold_pr_aucs)),
                "std_pr_auc": float(np.std(fold_pr_aucs)),
                "mean_roc_auc": float(np.mean(fold_roc_aucs)),
                "std_roc_auc": float(np.std(fold_roc_aucs)),
            }

    # ------------------------------------------------------------------ #
    # Best model selection & calibration
    # ------------------------------------------------------------------ #

    def _select_best_model(self):
        if not self.metrics:
            raise ValueError("No trained models available.")

        self.best_model_name = max(self.metrics.keys(), key=lambda m: self.metrics[m]["pr_auc"])
        self.best_model = self.models[self.best_model_name]

    def _calibrate_best_model(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray
    ):
        logger.info(f"Calibrating best model: {self.best_model_name}")

        calibrated = CalibratedClassifierCV(self.best_model, method="sigmoid", cv=3)
        calibrated.fit(X_train, y_train)

        y_scores = calibrated.predict_proba(X_test)[:, 1]
        y_pred = (y_scores >= 0.5).astype(int)

        calibrated_metrics = self._evaluate_model(y_test, y_pred, y_scores)
        self.metrics[self.best_model_name]["calibrated"] = calibrated_metrics
        self.best_model = calibrated

    # ------------------------------------------------------------------ #
    # Baseline comparison
    # ------------------------------------------------------------------ #

    def _compute_baseline(self, test_df: pd.DataFrame, y_test: np.ndarray):
        logger.info("Computing rule-based baseline...")

        candidate_cols = [
            c for c in test_df.columns
            if c.endswith("_match") or c.endswith("_equal") or c.endswith("_close")
        ]

        if "overall_similarity" in test_df.columns:
            candidate_cols.append("overall_similarity")

        if not candidate_cols:
            logger.warning("No baseline-compatible columns found.")
            return

        baseline_score = test_df[candidate_cols].fillna(0.0).mean(axis=1).values
        baseline_pred = (baseline_score >= 0.5).astype(int)

        baseline_metrics = self._evaluate_model(y_test, baseline_pred, baseline_score)
        self.metrics["baseline_rule"] = baseline_metrics

    # ------------------------------------------------------------------ #
    # Save outputs
    # ------------------------------------------------------------------ #

    def _save_best_model(self):
        path = self.output_dir / "best_attack_model.pkl"
        joblib.dump(self.best_model, path)
        logger.info(f"Saved best model to: {path}")

    def _save_reports(self):
        evaluation_path = self.output_dir / "evaluation_report.json"
        cv_path = self.output_dir / "cv_results.json"

        with open(evaluation_path, "w", encoding="utf-8") as f:
            json.dump(self.metrics, f, indent=2)

        with open(cv_path, "w", encoding="utf-8") as f:
            json.dump(self.cv_results, f, indent=2)

        logger.info(f"Saved evaluation report to: {evaluation_path}")
        logger.info(f"Saved CV results to: {cv_path}")