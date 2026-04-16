import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
from openai import OpenAI

from .prompts import (
    SYSTEM_PROMPT,
    RECORD_EXPLANATION_PROMPT,
    DATASET_SUMMARY_PROMPT,
    COMPARATIVE_PROMPT,
)

logger = logging.getLogger("agent7.llm_explainer")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


# Columns that are metadata, never real ML features
META_FEATURE_BLOCKLIST = {
    "record_id",
    "pair_index",
    "anon_id",
    "orig_id",
    "aux_id",
    "anon_index",
    "aux_index",
    "id",
    "ids",
    "pair_id",
    "label",
    "risk_score",
    "risk_level",
    "max_attack_score",
    "mean_attack_score",
    "pair_count",
    "pred_prob",
    "feature_value",
    "shap_value",
    "final_risk_score",
    "final_risk_level",
    "final_risk_score_0_1",
}

# Distance/similarity metrics that do NOT map to a single original column
_DISTANCE_METRICS = {
    "cosine_similarity",
    "euclidean_distance",
    "manhattan_distance",
    "jaccard_similarity",
    "overall_similarity",
    "cosine_sim",
    "euclidean_dist",
    "manhattan_dist",
}


def _shap_to_original_columns(shap_values: Dict[str, float]) -> Dict[str, float]:
    """
    Convert engineered feature names back to original column names where possible.
    Example:
    - age_diff -> age
    - gender_match -> gender
    - district_both_missing -> district
    """
    original: Dict[str, float] = {}

    suffixes = (
        "_days_diff",
        "_both_missing",
        "_same_year",
        "_diff",
        "_equal",
        "_match",
        "_similarity",
        "_ratio",
        "_score",
        "_normalized",
        "_close",
    )

    for feature, shap_val in shap_values.items():
        feature_l = str(feature).lower()

        if feature_l in _DISTANCE_METRICS:
            continue

        col = str(feature)
        for suffix in suffixes:
            if col.endswith(suffix):
                col = col[: -len(suffix)]
                break

        if col not in original or abs(shap_val) > abs(original[col]):
            original[col] = shap_val

    return original


def _get_primary_risk_column(df: pd.DataFrame) -> Optional[str]:
    """
    Choose the most suitable risk column available.
    """
    candidates = [
        "final_risk_score",
        "final_risk_score_0_1",
        "risk_score",
        "max_attack_score",
        "mean_attack_score",
    ]
    for col in candidates:
        if col in df.columns:
            return col
    return None


class LLMExplainer:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.3,
        max_tokens: int = 1000,
        timeout: int = 120,
    ):
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OpenAI API key not found. "
                "Set the OPENAI_API_KEY environment variable or pass api_key= directly."
            )

        self.client = OpenAI(api_key=resolved_key)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        logger.info("Agent 7: LLM Explainer initialized")
        logger.info("   Provider   : OpenAI")
        logger.info("   Model      : %s", model_name)
        logger.info("   Temperature: %s", temperature)

    # ------------------------------------------------------------------ #
    # LLM call helper
    # ------------------------------------------------------------------ #

    def _call_llm(self, user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

            explanation = response.choices[0].message.content or ""
            return explanation.strip()

        except Exception as e:
            logger.warning("LLM API error: %s", e)
            return f"[Error generating explanation: {str(e)}]"

    # ------------------------------------------------------------------ #
    # Record explanation
    # ------------------------------------------------------------------ #

    def explain_record(
        self,
        record_data: pd.Series,
        risk_score: float,
        shap_values: Dict[str, float],
        top_n: int = 5,
    ) -> str:
        record_info = []

        for col, val in record_data.items():
            if str(col).lower() in META_FEATURE_BLOCKLIST:
                record_info.append(f"- {col}: [ID hidden]")
                continue

            if pd.isna(val):
                record_info.append(f"- {col}: [Missing]")
            elif isinstance(val, (int, float, np.number)):
                record_info.append(f"- {col}: {float(val):.2f}")
            else:
                s = str(val).strip()
                record_info.append(f"- {col}: {s[:50]}")

        original_col_shap = _shap_to_original_columns(shap_values)
        sorted_features = sorted(
            original_col_shap.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )[:top_n]

        shap_features = []
        for feature, shap_val in sorted_features:
            direction = "increases" if shap_val > 0 else "decreases"
            shap_features.append(f"- {feature}: {direction} risk")

        prompt = RECORD_EXPLANATION_PROMPT.format(
            record_info="\n".join(record_info),
            risk_score=risk_score,
            shap_features="\n".join(shap_features) if shap_features else "- No dominant features available",
        )

        return self._call_llm(prompt)

    # ------------------------------------------------------------------ #
    # Dataset explanation
    # ------------------------------------------------------------------ #

    def explain_dataset(
        self,
        risk_scores: pd.Series,
        global_shap_importance: Dict[str, float],
        top_n: int = 10,
    ) -> str:
        total_records = len(risk_scores)
        avg_risk = float(risk_scores.mean()) if total_records else 0.0

        high_risk = int((risk_scores > 0.7).sum())
        medium_risk = int(((risk_scores >= 0.3) & (risk_scores <= 0.7)).sum())
        low_risk = int((risk_scores < 0.3).sum())

        high_risk_pct = (high_risk / total_records) * 100 if total_records else 0.0
        medium_risk_pct = (medium_risk / total_records) * 100 if total_records else 0.0
        low_risk_pct = (low_risk / total_records) * 100 if total_records else 0.0

        original_col_shap = _shap_to_original_columns(global_shap_importance)
        sorted_features = sorted(
            original_col_shap.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:top_n]

        global_shap_features = [
            f"- {feature}: {importance:.4f}"
            for feature, importance in sorted_features
        ]

        prompt = DATASET_SUMMARY_PROMPT.format(
            total_records=total_records,
            avg_risk=avg_risk,
            high_risk_count=high_risk,
            high_risk_pct=high_risk_pct,
            medium_risk_count=medium_risk,
            medium_risk_pct=medium_risk_pct,
            low_risk_count=low_risk,
            low_risk_pct=low_risk_pct,
            global_shap_features="\n".join(global_shap_features) if global_shap_features else "- No global SHAP features available",
        )

        return self._call_llm(prompt)

    # ------------------------------------------------------------------ #
    # Comparative explanation
    # ------------------------------------------------------------------ #

    def compare_risk_groups(
        self,
        high_risk_records: pd.DataFrame,
        low_risk_records: pd.DataFrame,
    ) -> str:
        risk_col_high = _get_primary_risk_column(high_risk_records)
        risk_col_low = _get_primary_risk_column(low_risk_records)

        high_risk_profile = []
        for col in high_risk_records.columns:
            if str(col).lower() in META_FEATURE_BLOCKLIST:
                continue

            if risk_col_high and col == risk_col_high:
                high_risk_profile.append(
                    f"- Average risk: {high_risk_records[col].mean():.4f}"
                )
            else:
                high_risk_profile.append(f"- {col}: {high_risk_records[col].dtype}")

        low_risk_profile = []
        for col in low_risk_records.columns:
            if str(col).lower() in META_FEATURE_BLOCKLIST:
                continue

            if risk_col_low and col == risk_col_low:
                low_risk_profile.append(
                    f"- Average risk: {low_risk_records[col].mean():.4f}"
                )
            else:
                low_risk_profile.append(f"- {col}: {low_risk_records[col].dtype}")

        prompt = COMPARATIVE_PROMPT.format(
            high_risk_profile="\n".join(high_risk_profile[:20]) if high_risk_profile else "- No high-risk profile available",
            low_risk_profile="\n".join(low_risk_profile[:20]) if low_risk_profile else "- No low-risk profile available",
        )

        return self._call_llm(prompt)

    # ------------------------------------------------------------------ #
    # Full report generation
    # ------------------------------------------------------------------ #

    def generate_full_report(
        self,
        risk_df: Optional[pd.DataFrame] = None,
        shap_global_df: Optional[pd.DataFrame] = None,
        shap_local_df: Optional[pd.DataFrame] = None,
        output_dir: str | Path = "data/llm_explanations",
        top_n_records: int = 10,
        risk_per_record_path: Optional[str | Path] = None,
        shap_global_path: Optional[str | Path] = None,
        shap_local_path: Optional[str | Path] = None,
        num_examples: Optional[int] = None,
    ) -> Dict[str, str]:
        if risk_df is None:
            if risk_per_record_path is None:
                raise ValueError("Either risk_df or risk_per_record_path must be provided.")
            risk_df = pd.read_csv(risk_per_record_path)

        if shap_global_df is None:
            if shap_global_path is None:
                raise ValueError("Either shap_global_df or shap_global_path must be provided.")
            shap_global_df = pd.read_csv(shap_global_path)

        if shap_local_df is None:
            if shap_local_path is None:
                raise ValueError("Either shap_local_df or shap_local_path must be provided.")
            shap_local_df = pd.read_csv(shap_local_path)

        if num_examples is not None:
            top_n_records = int(num_examples)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Agent 7: generating full explanation report...")
        logger.info("   Risk records      : %d", len(risk_df))
        logger.info("   Global SHAP rows  : %d", len(shap_global_df))
        logger.info("   Local SHAP rows   : %d", len(shap_local_df))

        risk_col = _get_primary_risk_column(risk_df)
        if risk_col is None:
            raise ValueError(
                "No risk column found. Expected one of: "
                "final_risk_score, final_risk_score_0_1, risk_score, max_attack_score, mean_attack_score"
            )

        # Normalize to 0-1 if needed
        risk_scores = risk_df[risk_col].astype(float)
        if risk_scores.max() > 1.0:
            risk_scores_01 = risk_scores / 100.0
        else:
            risk_scores_01 = risk_scores.copy()

        # Global SHAP dictionary
        feature_col = "feature" if "feature" in shap_global_df.columns else shap_global_df.columns[0]
        value_col = "mean_abs_shap" if "mean_abs_shap" in shap_global_df.columns else shap_global_df.columns[1]
        global_shap_importance = dict(zip(shap_global_df[feature_col], shap_global_df[value_col]))

        # Dataset summary
        dataset_summary = self.explain_dataset(risk_scores_01, global_shap_importance)

        # High vs low groups
        ranked = risk_df.copy()
        ranked["_risk_tmp"] = risk_scores_01.values

        high_risk_records = ranked.nlargest(min(20, len(ranked)), "_risk_tmp")
        low_risk_records = ranked.nsmallest(min(20, len(ranked)), "_risk_tmp")
        comparative_analysis = self.compare_risk_groups(high_risk_records, low_risk_records)

        # Record-level explanations
        record_explanations: List[Dict[str, Any]] = []
        explain_records = ranked.nlargest(min(top_n_records, len(ranked)), "_risk_tmp")

        shap_value_columns = [c for c in shap_local_df.columns if str(c).startswith("shap__")]

        for idx, (_, record) in enumerate(explain_records.iterrows(), start=1):
            if idx - 1 < len(shap_local_df):
                shap_row = shap_local_df.iloc[idx - 1]
                shap_dict = {
                    col.replace("shap__", ""): float(shap_row[col])
                    for col in shap_value_columns
                    if pd.notna(shap_row[col])
                }
            else:
                shap_dict = {}

            explanation = self.explain_record(
                record_data=record.drop(labels=["_risk_tmp"], errors="ignore"),
                risk_score=float(record["_risk_tmp"]),
                shap_values=shap_dict,
            )

            record_explanations.append(
                {
                    "record_rank": idx,
                    "risk_score": float(record["_risk_tmp"]),
                    "explanation": explanation,
                }
            )

        # Save outputs
        dataset_summary_path = output_dir / "dataset_summary.txt"
        comparative_path = output_dir / "comparative_analysis.txt"
        record_explanations_path = output_dir / "record_explanations.json"
        report_md_path = output_dir / "explanations_report.md"

        dataset_summary_path.write_text(dataset_summary, encoding="utf-8")
        comparative_path.write_text(comparative_analysis, encoding="utf-8")

        with open(record_explanations_path, "w", encoding="utf-8") as f:
            json.dump(record_explanations, f, indent=2, ensure_ascii=False)

        report_md = self._build_markdown_report(
            dataset_summary=dataset_summary,
            comparative_analysis=comparative_analysis,
            record_explanations=record_explanations,
            risk_column_used=risk_col,
        )
        report_md_path.write_text(report_md, encoding="utf-8")

        logger.info("Agent 7: explanation outputs saved")
        logger.info("   Dataset summary    : %s", dataset_summary_path)
        logger.info("   Comparative report : %s", comparative_path)
        logger.info("   Record explanations: %s", record_explanations_path)
        logger.info("   Markdown report    : %s", report_md_path)

        return {
            "dataset_summary_path": str(dataset_summary_path),
            "comparative_analysis_path": str(comparative_path),
            "record_explanations_path": str(record_explanations_path),
            "report_markdown_path": str(report_md_path),
        }

    # ------------------------------------------------------------------ #
    # Markdown builder
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_markdown_report(
        dataset_summary: str,
        comparative_analysis: str,
        record_explanations: List[Dict[str, Any]],
        risk_column_used: str,
    ) -> str:
        lines = [
            "# Agent 7 LLM Explanation Report",
            "",
            f"**Risk column used:** `{risk_column_used}`",
            "",
            "## Dataset Summary",
            "",
            dataset_summary,
            "",
            "## Comparative Analysis",
            "",
            comparative_analysis,
            "",
            "## Record-Level Explanations",
            "",
        ]

        for item in record_explanations:
            lines.extend(
                [
                    f"### Record Rank {item['record_rank']}",
                    "",
                    f"- Risk Score: {item['risk_score']:.4f}",
                    "",
                    item["explanation"],
                    "",
                ]
            )

        return "\n".join(lines)