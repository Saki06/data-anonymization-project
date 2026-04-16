from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from ...utils.logger import get_logger

logger = get_logger("corrected_data_inspector.semantic_analyzer")


class SemanticAnalyzer:
    """
    Lightweight privacy-focused analyzer.

    This module intentionally does NOT perform domain inference.
    It consumes optional identifier-detector output from another component,
    then adds:
    - quasi-identifier hints
    - sensitive column hints
    - dataset granularity
    - likely join keys between files
    """

    def analyze_dataframe(
        self,
        df: pd.DataFrame,
        identifier_results: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        identifier_results = identifier_results or {}
        identifier_columns = identifier_results.get("identifiers", []) or identifier_results.get("identifier_columns", []) or []
        identifier_columns = [c for c in identifier_columns if c in df.columns]

        column_roles: Dict[str, str] = {}
        quasi_identifiers: List[str] = []
        sensitive_columns: List[str] = []

        for col in df.columns:
            if col in identifier_columns:
                column_roles[col] = "identifier"
                continue

            series = df[col]
            sensitive = self._looks_sensitive(col)
            qid_score = self._quasi_identifier_score(series, col)

            if sensitive:
                sensitive_columns.append(col)
                column_roles[col] = "sensitive_attribute"
            elif qid_score >= 0.55:
                quasi_identifiers.append(col)
                column_roles[col] = "quasi_identifier"
            elif pd.api.types.is_datetime64_any_dtype(series):
                column_roles[col] = "temporal"
            elif pd.api.types.is_numeric_dtype(series):
                column_roles[col] = "numeric_measure"
            else:
                column_roles[col] = "categorical_or_text"

        return {
            "identifiers": identifier_columns,
            "quasi_identifiers": quasi_identifiers,
            "sensitive_columns": sensitive_columns,
            "granularity": self._infer_granularity(df, identifier_columns),
            "column_roles": column_roles,
            "confidence": self._infer_confidence(identifier_columns, quasi_identifiers),
        }

    def analyze_files(
        self,
        files: Dict[str, pd.DataFrame],
        identifier_results_by_file: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        identifier_results_by_file = identifier_results_by_file or {}
        per_file = {
            name: self.analyze_dataframe(df, identifier_results_by_file.get(name))
            for name, df in files.items()
        }

        relationships = []
        names = list(files.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                rel = self._find_relationship(names[i], files[names[i]], per_file[names[i]], names[j], files[names[j]], per_file[names[j]])
                if rel is not None:
                    relationships.append(rel)

        return {
            "per_file": per_file,
            "relationships": relationships,
        }

    def _quasi_identifier_score(self, series: pd.Series, name: str) -> float:
        non_null = series.dropna()
        if len(series) == 0 or non_null.empty:
            return 0.0
        unique_ratio = non_null.nunique() / len(series)
        score = 0.0
        if pd.api.types.is_datetime64_any_dtype(series):
            score += 0.4
        elif pd.api.types.is_numeric_dtype(series):
            if 0.02 <= unique_ratio <= 0.85:
                score += 0.35
        else:
            if 0.01 <= unique_ratio <= 0.60:
                score += 0.35

        lowered = name.lower()
        if any(token in lowered for token in ["age", "sex", "gender", "birth", "district", "region", "city", "province", "zip", "post", "occupation", "education", "marital"]):
            score += 0.35
        if series.isna().mean() <= 0.1:
            score += 0.1
        return min(score, 1.0)

    def _looks_sensitive(self, name: str) -> bool:
        lowered = name.lower()
        return any(token in lowered for token in [
            "diagnosis", "disease", "medical", "treatment", "salary", "income",
            "wage", "religion", "ethnicity", "race", "political", "claim",
            "loan", "debt", "insurance", "hiv", "cancer", "disability",
        ])

    def _infer_granularity(self, df: pd.DataFrame, identifiers: List[str]) -> str:
        names = [c.lower() for c in df.columns]
        if any("household" in c or c == "hh" for c in names):
            return "household"
        if any(token in c for c in names for token in ["transaction", "payment", "order", "invoice", "sale"]):
            return "transaction"
        if any(token in c for c in names for token in ["event", "visit", "incident", "encounter"]):
            return "event"
        if any(token in c for c in names for token in ["member", "person", "patient", "student", "customer", "client", "employee"]):
            return "individual"
        if identifiers:
            return "entity"
        return "record"

    def _infer_confidence(self, identifiers: List[str], qids: List[str]) -> str:
        if identifiers:
            return "high"
        if len(qids) >= 2:
            return "medium"
        return "low"

    def _find_relationship(
        self,
        file1: str,
        df1: pd.DataFrame,
        analysis1: Dict[str, Any],
        file2: str,
        df2: pd.DataFrame,
        analysis2: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        common = [c for c in df1.columns if c in df2.columns]
        if not common:
            return None

        join_scores: Dict[str, float] = {}
        for col in common:
            score = 0.0
            if col in analysis1.get("identifiers", []) or col in analysis2.get("identifiers", []):
                score += 40.0
            uniq1 = df1[col].dropna().nunique() / max(len(df1), 1)
            uniq2 = df2[col].dropna().nunique() / max(len(df2), 1)
            score += ((uniq1 + uniq2) / 2.0) * 40.0
            overlap = self._overlap_ratio(df1[col], df2[col])
            score += overlap * 20.0
            join_scores[col] = score

        join_keys = [c for c, s in sorted(join_scores.items(), key=lambda x: x[1], reverse=True) if s >= 35.0][:3]
        if not join_keys:
            return None

        return {
            "file1": file1,
            "file2": file2,
            "join_keys": join_keys,
            "common_columns": common,
            "relationship_type": self._relationship_type(analysis1.get("granularity", "record"), analysis2.get("granularity", "record")),
        }

    @staticmethod
    def _relationship_type(g1: str, g2: str) -> str:
        if g1 == g2:
            return "same_level"
        if "transaction" in {g1, g2} or "event" in {g1, g2}:
            return "event_to_entity"
        if {g1, g2} == {"household", "individual"}:
            return "parent_child"
        return "related"

    @staticmethod
    def _overlap_ratio(left: pd.Series, right: pd.Series) -> float:
        left_values = set(left.dropna().astype(str).head(1000))
        right_values = set(right.dropna().astype(str).head(1000))
        if not left_values or not right_values:
            return 0.0
        return len(left_values & right_values) / max(min(len(left_values), len(right_values)), 1)
