from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from ...utils.logger import get_logger

logger = get_logger("agent3.pair_generator")


class PairGenerator:
    """
    Agent 3: Pair Generation + Feature Engineering

    Inputs:
    - auxiliary dataset
    - anonymized dataset
    - Agent 2 final config

    Responsibilities:
    - resolve final QI mapping
    - generate positive / negative pairs
    - engineer numeric / categorical / datetime similarity features
    - save train/test pair datasets
    """

    def __init__(
        self,
        output_dir: Path | str = "data/pairs",
        negative_ratio: float = 1.0,
        test_size: float = 0.2,
        random_state: int = 42,
        use_suggested_mappings: bool = True,
        hard_negative_ratio: float = 0.5,
        numeric_tolerance: float = 0.05,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.negative_ratio = negative_ratio
        self.test_size = test_size
        self.random_state = random_state
        self.use_suggested_mappings = use_suggested_mappings
        self.hard_negative_ratio = hard_negative_ratio
        self.numeric_tolerance = numeric_tolerance

        self.rng = np.random.default_rng(random_state)

    # ------------------------------------------------------------------ #
    # Public entrypoint
    # ------------------------------------------------------------------ #

    def run(
        self,
        auxiliary_path: Path | str,
        anonymized_path: Path | str,
        agent2_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        logger.info("🚀 Agent 3: Pair Generator started")

        aux_df = pd.read_csv(auxiliary_path)
        anon_df = pd.read_csv(anonymized_path)

        logger.info("   Auxiliary dataset : %s", aux_df.shape)
        logger.info("   Anonymized dataset: %s", anon_df.shape)

        aux_df = self._normalize_dataframe(aux_df)
        anon_df = self._normalize_dataframe(anon_df)

        resolved = self._resolve_final_qi_mapping(aux_df, anon_df, agent2_config)

        logger.info("✅ Final resolved QI mapping: %s", resolved["qi_mapping"])
        logger.info("✅ Direct identifiers excluded: %s", resolved["direct_identifiers"])
        logger.info("✅ Sensitive attributes excluded: %s", resolved["sensitive_attributes"])

        positive_pairs = self._generate_positive_pairs(aux_df, anon_df, resolved)
        negative_pairs = self._generate_negative_pairs(aux_df, anon_df, resolved, len(positive_pairs))

        logger.info("   Positive pairs: %d", len(positive_pairs))
        logger.info("   Negative pairs: %d", len(negative_pairs))

        all_pairs = positive_pairs + negative_pairs
        if not all_pairs:
            raise ValueError("No pairs generated. Check mappings or input datasets.")

        pair_df = pd.DataFrame(all_pairs)

        train_df, test_df = train_test_split(
            pair_df,
            test_size=self.test_size,
            random_state=self.random_state,
            stratify=pair_df["label"] if pair_df["label"].nunique() > 1 else None,
        )

        pair_path = self.output_dir / "pair_dataset.csv"
        train_path = self.output_dir / "train_pairs.csv"
        test_path = self.output_dir / "test_pairs.csv"
        report_path = self.output_dir / "pair_generation_report.json"

        pair_df.to_csv(pair_path, index=False)
        train_df.to_csv(train_path, index=False)
        test_df.to_csv(test_path, index=False)

        report = {
            "auxiliary_shape": list(aux_df.shape),
            "anonymized_shape": list(anon_df.shape),
            "resolved_qi_mapping": resolved["qi_mapping"],
            "direct_identifiers": resolved["direct_identifiers"],
            "sensitive_attributes": resolved["sensitive_attributes"],
            "positive_pair_count": int(len(positive_pairs)),
            "negative_pair_count": int(len(negative_pairs)),
            "total_pair_count": int(len(pair_df)),
            "feature_columns": [c for c in pair_df.columns if c not in {"aux_index", "anon_index", "label"}],
            "train_size": int(len(train_df)),
            "test_size": int(len(test_df)),
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        logger.info("✅ Agent 3 complete")
        logger.info("   Pair dataset: %s", pair_path)
        logger.info("   Train pairs : %s", train_path)
        logger.info("   Test pairs  : %s", test_path)

        return {
            "pair_dataset_path": str(pair_path),
            "train_pairs_path": str(train_path),
            "test_pairs_path": str(test_path),
            "report_path": str(report_path),
            "report": report,
        }

    # ------------------------------------------------------------------ #
    # Resolve final config
    # ------------------------------------------------------------------ #

    def _resolve_final_qi_mapping(
        self,
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
        agent2_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        direct_identifiers = self._normalize_name_list(agent2_config.get("direct_identifiers", []))
        quasi_identifiers = self._normalize_name_list(agent2_config.get("quasi_identifiers", []))
        sensitive_attributes = self._normalize_name_list(agent2_config.get("sensitive_attributes", []))
        explicit_mapping = self._normalize_mapping(agent2_config.get("column_mapping", {}))
        suggested_mappings = agent2_config.get("suggested_mappings", {}) or {}

        aux_cols = set(aux_df.columns)
        anon_cols = set(anon_df.columns)

        qi_mapping: Dict[str, str] = {}

        for aux_qi in quasi_identifiers:
            if aux_qi in direct_identifiers or aux_qi in sensitive_attributes:
                continue

            # 1. explicit mapping
            if aux_qi in explicit_mapping:
                target = self._normalize_name(explicit_mapping[aux_qi])
                if aux_qi in aux_cols and target in anon_cols:
                    qi_mapping[aux_qi] = target
                    continue

            # 2. same-name mapping
            if aux_qi in aux_cols and aux_qi in anon_cols:
                qi_mapping[aux_qi] = aux_qi
                continue

            # 3. suggested mapping
            if self.use_suggested_mappings and aux_qi in suggested_mappings:
                candidates = suggested_mappings.get(aux_qi, [])
                if candidates and isinstance(candidates, list):
                    first = candidates[0]
                    target = self._normalize_name(first.get("candidate", ""))
                    if aux_qi in aux_cols and target in anon_cols:
                        qi_mapping[aux_qi] = target
                        continue

        if not qi_mapping:
            raise ValueError("No usable quasi-identifier mappings resolved from Agent 2 config.")

        return {
            "direct_identifiers": direct_identifiers,
            "quasi_identifiers": quasi_identifiers,
            "sensitive_attributes": sensitive_attributes,
            "qi_mapping": qi_mapping,
        }

    # ------------------------------------------------------------------ #
    # Positive / negative pair generation
    # ------------------------------------------------------------------ #

    def _generate_positive_pairs(
        self,
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
        resolved: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        qi_mapping = resolved["qi_mapping"]

        aux_indices_used = set()
        anon_indices_used = set()
        pairs: List[Dict[str, Any]] = []

        # candidate blocking columns = exact-match categorical columns among mapped QIs
        blocking_cols = []
        for aux_col, anon_col in qi_mapping.items():
            if aux_col in aux_df.columns and anon_col in anon_df.columns:
                if self._dtype_group(aux_df[aux_col]) == "categorical" and self._dtype_group(anon_df[anon_col]) == "categorical":
                    blocking_cols.append((aux_col, anon_col))

        for aux_idx, aux_row in aux_df.iterrows():
            best_match_idx = None
            best_score = -1.0

            # block candidates first if possible
            candidate_idx = anon_df.index.tolist()
            if blocking_cols:
                candidate_mask = pd.Series(True, index=anon_df.index)
                for a_col, b_col in blocking_cols[:2]:
                    aux_val = aux_row[a_col]
                    if pd.isna(aux_val):
                        continue
                    candidate_mask &= (anon_df[b_col] == aux_val)
                blocked = anon_df[candidate_mask]
                if not blocked.empty:
                    candidate_idx = blocked.index.tolist()

            for anon_idx in candidate_idx:
                if anon_idx in anon_indices_used:
                    continue
                anon_row = anon_df.loc[anon_idx]
                sim = self._row_similarity(aux_row, anon_row, qi_mapping, aux_df, anon_df)
                if sim > best_score:
                    best_score = sim
                    best_match_idx = anon_idx

            if best_match_idx is not None and best_score >= 0.6:
                anon_row = anon_df.loc[best_match_idx]
                pair = self._build_pair_features(
                    aux_index=aux_idx,
                    anon_index=best_match_idx,
                    aux_row=aux_row,
                    anon_row=anon_row,
                    qi_mapping=qi_mapping,
                    aux_df=aux_df,
                    anon_df=anon_df,
                    label=1,
                )
                pairs.append(pair)
                aux_indices_used.add(aux_idx)
                anon_indices_used.add(best_match_idx)

        return pairs

    def _generate_negative_pairs(
        self,
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
        resolved: Dict[str, Any],
        positive_count: int,
    ) -> List[Dict[str, Any]]:
        qi_mapping = resolved["qi_mapping"]
        target_count = max(int(positive_count * self.negative_ratio), 1)

        negatives: List[Dict[str, Any]] = []
        tried = set()

        aux_indices = list(aux_df.index)
        anon_indices = list(anon_df.index)
        total_pair_space = len(aux_indices) * len(anon_indices)

        hard_target = int(target_count * self.hard_negative_ratio)

        # 1. hard negatives: similar but not too similar
        while len(negatives) < hard_target and len(tried) < total_pair_space:
            aux_idx = int(self.rng.choice(aux_indices))
            anon_idx = int(self.rng.choice(anon_indices))
            key = (aux_idx, anon_idx)
            if key in tried:
                continue
            tried.add(key)

            aux_row = aux_df.loc[aux_idx]
            anon_row = anon_df.loc[anon_idx]

            sim = self._row_similarity(aux_row, anon_row, qi_mapping, aux_df, anon_df)
            if 0.4 <= sim < 0.8:
                negatives.append(
                    self._build_pair_features(
                        aux_index=aux_idx,
                        anon_index=anon_idx,
                        aux_row=aux_row,
                        anon_row=anon_row,
                        qi_mapping=qi_mapping,
                        aux_df=aux_df,
                        anon_df=anon_df,
                        label=0,
                    )
                )

        # If hard-negative search consumed the full pair space, reset so random negatives can still be sampled.
        if len(negatives) < target_count and len(tried) >= total_pair_space:
            tried = set()

        # 2. random negatives
        while len(negatives) < target_count and len(tried) < total_pair_space:
            aux_idx = int(self.rng.choice(aux_indices))
            anon_idx = int(self.rng.choice(anon_indices))
            key = (aux_idx, anon_idx)
            if key in tried:
                continue
            tried.add(key)

            aux_row = aux_df.loc[aux_idx]
            anon_row = anon_df.loc[anon_idx]

            negatives.append(
                self._build_pair_features(
                    aux_index=aux_idx,
                    anon_index=anon_idx,
                    aux_row=aux_row,
                    anon_row=anon_row,
                    qi_mapping=qi_mapping,
                    aux_df=aux_df,
                    anon_df=anon_df,
                    label=0,
                )
            )

        return negatives

    # ------------------------------------------------------------------ #
    # Feature engineering
    # ------------------------------------------------------------------ #

    def _build_pair_features(
        self,
        aux_index: int,
        anon_index: int,
        aux_row: pd.Series,
        anon_row: pd.Series,
        qi_mapping: Dict[str, str],
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
        label: int,
    ) -> Dict[str, Any]:
        features: Dict[str, Any] = {
            "aux_index": int(aux_index),
            "anon_index": int(anon_index),
            "label": int(label),
        }

        similarity_scores: List[float] = []

        for aux_col, anon_col in qi_mapping.items():
            aux_val = aux_row[aux_col]
            anon_val = anon_row[anon_col]

            aux_series = aux_df[aux_col]
            anon_series = anon_df[anon_col]
            dtype_group = self._choose_common_dtype(aux_series, anon_series)

            if dtype_group == "numeric":
                diff = self._numeric_diff(aux_val, anon_val)
                ratio = self._numeric_ratio(aux_val, anon_val)
                close = self._numeric_close(aux_val, anon_val, aux_series, anon_series)

                features[f"{aux_col}_diff"] = diff
                features[f"{aux_col}_ratio"] = ratio
                features[f"{aux_col}_close"] = close

                if pd.notna(diff):
                    similarity_scores.append(max(0.0, 1.0 - min(diff, 1.0)))
                else:
                    similarity_scores.append(0.0)

            elif dtype_group == "datetime":
                day_diff = self._datetime_diff_days(aux_val, anon_val)
                same_year = self._same_year(aux_val, anon_val)

                features[f"{aux_col}_days_diff"] = day_diff
                features[f"{aux_col}_same_year"] = same_year

                if pd.notna(day_diff):
                    similarity_scores.append(max(0.0, 1.0 - min(day_diff / 365.0, 1.0)))
                else:
                    similarity_scores.append(0.0)

            else:
                exact = self._categorical_match(aux_val, anon_val)
                missing_same = int(pd.isna(aux_val) and pd.isna(anon_val))

                features[f"{aux_col}_match"] = exact
                features[f"{aux_col}_both_missing"] = missing_same

                similarity_scores.append(float(exact))

        features["overall_similarity"] = float(np.mean(similarity_scores)) if similarity_scores else 0.0
        return features

    # ------------------------------------------------------------------ #
    # Similarity helpers
    # ------------------------------------------------------------------ #

    def _row_similarity(
        self,
        aux_row: pd.Series,
        anon_row: pd.Series,
        qi_mapping: Dict[str, str],
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
    ) -> float:
        scores: List[float] = []

        for aux_col, anon_col in qi_mapping.items():
            aux_val = aux_row[aux_col]
            anon_val = anon_row[anon_col]

            aux_series = aux_df[aux_col]
            anon_series = anon_df[anon_col]

            dtype_group = self._choose_common_dtype(aux_series, anon_series)

            if dtype_group == "numeric":
                diff = self._numeric_diff(aux_val, anon_val)
                if pd.notna(diff):
                    scores.append(max(0.0, 1.0 - min(diff, 1.0)))
                else:
                    scores.append(0.0)

            elif dtype_group == "datetime":
                day_diff = self._datetime_diff_days(aux_val, anon_val)
                if pd.notna(day_diff):
                    scores.append(max(0.0, 1.0 - min(day_diff / 365.0, 1.0)))
                else:
                    scores.append(0.0)

            else:
                scores.append(float(self._categorical_match(aux_val, anon_val)))

        return float(np.mean(scores)) if scores else 0.0

    # ------------------------------------------------------------------ #
    # Type helpers
    # ------------------------------------------------------------------ #

    def _choose_common_dtype(self, aux_series: pd.Series, anon_series: pd.Series) -> str:
        left = self._dtype_group(aux_series)
        right = self._dtype_group(anon_series)

        if left == right:
            return left

        if "numeric" in {left, right}:
            return "numeric"
        if "datetime" in {left, right}:
            return "datetime"
        return "categorical"

    @staticmethod
    def _dtype_group(series: pd.Series) -> str:
        if pd.api.types.is_bool_dtype(series):
            return "categorical"
        if pd.api.types.is_numeric_dtype(series):
            return "numeric"
        if pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"
        return "categorical"

    # ------------------------------------------------------------------ #
    # Numeric feature helpers
    # ------------------------------------------------------------------ #

    def _numeric_diff(self, a: Any, b: Any) -> float:
        if pd.isna(a) or pd.isna(b):
            return np.nan
        try:
            a = float(a)
            b = float(b)
            denom = max(abs(a), abs(b), 1.0)
            return abs(a - b) / denom
        except Exception:
            return np.nan

    def _numeric_ratio(self, a: Any, b: Any) -> float:
        if pd.isna(a) or pd.isna(b):
            return np.nan
        try:
            a = float(a)
            b = float(b)
            if b == 0:
                return np.nan
            return a / b
        except Exception:
            return np.nan

    def _numeric_close(
        self,
        a: Any,
        b: Any,
        aux_series: pd.Series,
        anon_series: pd.Series,
    ) -> int:
        if pd.isna(a) or pd.isna(b):
            return 0
        try:
            a = float(a)
            b = float(b)
            combined = pd.concat([aux_series, anon_series], ignore_index=True)
            std = pd.to_numeric(combined, errors="coerce").std()
            tolerance = std * self.numeric_tolerance if pd.notna(std) and std > 0 else 1.0
            return int(abs(a - b) <= tolerance)
        except Exception:
            return 0

    # ------------------------------------------------------------------ #
    # Datetime feature helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _datetime_diff_days(a: Any, b: Any) -> float:
        a = pd.to_datetime(a, errors="coerce")
        b = pd.to_datetime(b, errors="coerce")
        if pd.isna(a) or pd.isna(b):
            return np.nan
        return float(abs((a - b).days))

    @staticmethod
    def _same_year(a: Any, b: Any) -> int:
        a = pd.to_datetime(a, errors="coerce")
        b = pd.to_datetime(b, errors="coerce")
        if pd.isna(a) or pd.isna(b):
            return 0
        return int(a.year == b.year)

    # ------------------------------------------------------------------ #
    # Categorical feature helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _categorical_match(a: Any, b: Any) -> int:
        if pd.isna(a) or pd.isna(b):
            return 0
        return int(str(a).strip().lower() == str(b).strip().lower())

    # ------------------------------------------------------------------ #
    # Normalization helpers
    # ------------------------------------------------------------------ #

    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out.columns = [self._normalize_name(c) for c in out.columns]

        for col in out.columns:
            out[col] = self._normalize_series(out[col])

        return out

    def _normalize_series(self, series: pd.Series) -> pd.Series:
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
            return series

        cleaned = series.copy()

        if cleaned.dtype == object or str(cleaned.dtype).startswith("string"):
            cleaned = cleaned.apply(self._clean_string)

            numeric_candidate = pd.to_numeric(cleaned, errors="ignore")
            if pd.api.types.is_numeric_dtype(numeric_candidate):
                return numeric_candidate

            datetime_candidate = pd.to_datetime(cleaned, errors="coerce")
            if datetime_candidate.notna().mean() >= 0.9 and datetime_candidate.notna().sum() > 0:
                return datetime_candidate

            return cleaned.astype("string")

        return cleaned

    @staticmethod
    def _normalize_name(name: Any) -> str:
        text = str(name).strip().lower()
        text = text.replace("/", "_").replace("-", "_").replace(" ", "_")
        while "__" in text:
            text = text.replace("__", "_")
        return text.strip("_")

    @staticmethod
    def _normalize_name_list(values: List[Any]) -> List[str]:
        out: List[str] = []
        seen = set()
        for v in values:
            nv = PairGenerator._normalize_name(v)
            if nv and nv not in seen:
                out.append(nv)
                seen.add(nv)
        return out

    @staticmethod
    def _normalize_mapping(mapping: Dict[Any, Any]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for k, v in mapping.items():
            nk = PairGenerator._normalize_name(k)
            nv = PairGenerator._normalize_name(v)
            if nk and nv:
                out[nk] = nv
        return out

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