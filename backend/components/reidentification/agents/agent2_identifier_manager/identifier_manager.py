from __future__ import annotations

import json
import logging
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


# ===========================================================================
# Helpers
# ===========================================================================

def _normalize_name(name: Any) -> str:
    text = str(name).strip().lower()
    text = text.replace("/", "_").replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def _normalize_name_list(values: Optional[List[Any]]) -> List[str]:
    if not values:
        return []
    out: List[str] = []
    seen = set()
    for value in values:
        norm = _normalize_name(value)
        if norm and norm not in seen:
            out.append(norm)
            seen.add(norm)
    return out


def _normalize_mapping(mapping: Optional[Dict[Any, Any]]) -> Dict[str, str]:
    if not mapping:
        return {}
    normalized: Dict[str, str] = {}
    for k, v in mapping.items():
        nk = _normalize_name(k)
        nv = _normalize_name(v)
        if nk and nv:
            normalized[nk] = nv
    return normalized


def _normalize_value(value: Any) -> Optional[str]:
    if pd.isna(value):
        return None
    text = str(value).strip().lower()
    if text in {"", "na", "n/a", "null", "none", "nan", "missing", "unknown"}:
        return None
    return text


def _is_low_cardinality(series: pd.Series, threshold: int = 100) -> bool:
    non_null = series.dropna()
    if non_null.empty:
        return False
    return int(non_null.nunique()) <= threshold


# ===========================================================================
# ColumnListValidator
# ===========================================================================

class ColumnListValidator:
    """
    Validates user-provided column lists against auxiliary and anonymized datasets.
    """

    def validate_list(
        self,
        values: List[str],
        df_auxiliary: pd.DataFrame,
        df_anonymized: pd.DataFrame,
        label: str,
        require_in_both: bool = True,
    ) -> Dict[str, Any]:
        aux_columns = set(df_auxiliary.columns)
        anon_columns = set(df_anonymized.columns)
        common_columns = aux_columns & anon_columns

        logger.info("🔍 Validating %s list", label)
        logger.info("   Provided values : %d", len(values))
        logger.info("   Auxiliary cols  : %d", len(aux_columns))
        logger.info("   Anonymized cols : %d", len(anon_columns))
        logger.info("   Common columns  : %d", len(common_columns))

        result: Dict[str, Any] = {
            "valid": [],
            "invalid": [],
            "warnings": [],
            "suggestions": {},
            "is_valid": True,
        }

        if not values:
            result["warnings"].append(f"⚠️ Empty {label} list provided")
            result["is_valid"] = False
            return result

        for col in values:
            in_aux = col in aux_columns
            in_anon = col in anon_columns
            valid = (in_aux and in_anon) if require_in_both else (in_aux or in_anon)

            if valid:
                result["valid"].append(col)
            else:
                result["invalid"].append(col)

                if not in_aux and not in_anon:
                    warn = f"❌ '{col}' not found in either dataset"
                elif not in_aux:
                    warn = f"⚠️ '{col}' not found in auxiliary dataset"
                else:
                    warn = f"⚠️ '{col}' not found in anonymized dataset"

                result["warnings"].append(warn)
                logger.warning("   %s", warn)

                suggestions = self._suggest(
                    invalid_col=col,
                    aux_columns=aux_columns,
                    anon_columns=anon_columns,
                    require_in_both=require_in_both,
                )
                if suggestions:
                    result["suggestions"][col] = suggestions
                    logger.info("   💡 Suggestions for '%s': %s", col, suggestions)

        if len(result["valid"]) == 0:
            result["warnings"].append(f"❌ No valid {label} columns found")
            result["is_valid"] = False
            logger.error("❌ Validation failed: no valid %s columns", label)
        elif len(result["valid"]) < len(values) * 0.5:
            warn = (
                f"⚠️ Only {len(result['valid'])}/{len(values)} {label} columns are valid. "
                "Please review the input."
            )
            result["warnings"].append(warn)
            logger.warning(warn)
        else:
            logger.info("✅ %s validation passed: %d/%d valid", label, len(result["valid"]), len(values))

        return result

    def _suggest(
        self,
        invalid_col: str,
        aux_columns: Set[str],
        anon_columns: Set[str],
        require_in_both: bool = True,
        max_suggestions: int = 3,
    ) -> List[str]:
        candidate_pool = list((aux_columns & anon_columns) if require_in_both else (aux_columns | anon_columns))
        return get_close_matches(invalid_col, candidate_pool, n=max_suggestions, cutoff=0.6)


# ===========================================================================
# ValueBasedMappingSuggester
# ===========================================================================

class ValueBasedMappingSuggester:
    """
    Suggests mappings when column names differ but raw values overlap strongly.
    Best for low-cardinality categorical / code-like columns.
    """

    def __init__(
        self,
        overlap_threshold: float = 0.8,
        max_unique_values: int = 100,
        max_suggestions_per_column: int = 3,
    ) -> None:
        self.overlap_threshold = overlap_threshold
        self.max_unique_values = max_unique_values
        self.max_suggestions_per_column = max_suggestions_per_column

    def suggest_mappings(
        self,
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
        candidate_columns: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        suggestions: Dict[str, List[Dict[str, Any]]] = {}

        aux_candidates = [c for c in candidate_columns if c in aux_df.columns]
        anon_candidates = [c for c in candidate_columns if c in anon_df.columns]

        for aux_col in aux_candidates:
            aux_series = aux_df[aux_col]

            if not self._is_mapping_candidate(aux_series):
                continue

            scored_matches: List[Dict[str, Any]] = []

            for anon_col in anon_candidates:
                if aux_col == anon_col:
                    continue

                anon_series = anon_df[anon_col]
                if not self._is_mapping_candidate(anon_series):
                    continue

                overlap_score = self._value_overlap_ratio(aux_series, anon_series)
                if overlap_score >= self.overlap_threshold:
                    scored_matches.append(
                        {
                            "candidate": anon_col,
                            "overlap_score": round(overlap_score, 4),
                            "reason": "high_value_overlap",
                        }
                    )

            if scored_matches:
                scored_matches.sort(key=lambda x: x["overlap_score"], reverse=True)
                suggestions[aux_col] = scored_matches[: self.max_suggestions_per_column]

        return suggestions

    def _is_mapping_candidate(self, series: pd.Series) -> bool:
        if pd.api.types.is_numeric_dtype(series):
            return False
        return _is_low_cardinality(series, threshold=self.max_unique_values)

    def _value_overlap_ratio(self, left: pd.Series, right: pd.Series) -> float:
        left_values = {
            v for v in (_normalize_value(x) for x in left.dropna())
            if v is not None
        }
        right_values = {
            v for v in (_normalize_value(x) for x in right.dropna())
            if v is not None
        }

        if not left_values or not right_values:
            return 0.0

        intersection = len(left_values & right_values)
        denominator = min(len(left_values), len(right_values))
        return intersection / denominator if denominator else 0.0


# ===========================================================================
# IdentifierMapper
# ===========================================================================

class IdentifierMapper:
    """
    Validates auxiliary->anonymized column mappings from user config.
    """

    def map_columns_from_config(
        self,
        config: Dict[str, Any],
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
    ) -> Tuple[Dict[str, str], List[str]]:
        mapping: Dict[str, str] = {}
        invalid: List[str] = []

        logger.info("🔗 Validating column mappings from user configuration")

        for key in ("identifier_mapping", "quasi_identifier_mapping"):
            raw_mapping = config.get(key, {})
            if not isinstance(raw_mapping, dict):
                invalid.append(f"{key}: must be a dictionary")
                logger.warning("   ✗ Invalid %s: must be a dictionary", key)
                continue

            for aux_col, anon_col in raw_mapping.items():
                if aux_col in aux_df.columns and anon_col in anon_df.columns:
                    mapping[aux_col] = anon_col
                    logger.info("   ✓ %s: '%s' → '%s'", key, aux_col, anon_col)
                else:
                    entry = f"{aux_col} → {anon_col}"
                    invalid.append(entry)
                    logger.warning("   ✗ Invalid %s: '%s' → '%s'", key, aux_col, anon_col)

        logger.info("📊 Mapping result — Valid: %d | Invalid: %d", len(mapping), len(invalid))
        return mapping, invalid


# ===========================================================================
# IdentifierManager
# ===========================================================================

class IdentifierManager:
    """
    Agent 2 for your architecture:

    - DOES NOT detect identifiers automatically
    - EXPECTS upstream component to provide:
        * direct_identifiers
        * quasi_identifiers
        * sensitive_attributes
        * optional identifier/quasi_identifier mappings
    - VALIDATES and SAVES a clean final configuration
    - SUGGESTS value-based mappings when names differ but values overlap
    """

    def __init__(
        self,
        data_dir: str = "data",
        overlap_threshold: float = 0.8,
        max_unique_values_for_value_mapping: int = 100,
    ):
        self.data_dir = Path(data_dir)
        self.identifiers_dir = self.data_dir / "identifiers"
        self.identifiers_dir.mkdir(parents=True, exist_ok=True)

        self.list_validator = ColumnListValidator()
        self.mapper = IdentifierMapper()
        self.mapping_suggester = ValueBasedMappingSuggester(
            overlap_threshold=overlap_threshold,
            max_unique_values=max_unique_values_for_value_mapping,
        )

        logger.info("✅ Agent 2: IdentifierManager initialized")
        logger.info("   Data directory       : %s", self.data_dir)
        logger.info("   Identifiers directory: %s", self.identifiers_dir)

    def process_identifiers(
        self,
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
        user_config: Optional[Dict[str, Any]] = None,
        mode: str = "user",
    ) -> Dict[str, Any]:
        logger.info("=" * 80)
        logger.info("🚀 AGENT 2: IDENTIFIER MANAGER - STARTING")
        logger.info("=" * 80)
        logger.info("   Auxiliary dataset : %s", aux_df.shape)
        logger.info("   Anonymized dataset: %s", anon_df.shape)

        result: Dict[str, Any] = {
            "mode": "user",
            "validation": {},
            "mapping": {},
            "suggested_mappings": {},
            "final_config": {},
            "warnings": [],
            "success": False,
        }

        if mode != "user":
            msg = f"IdentifierManager only supports mode='user'. Received mode='{mode}'."
            logger.error("❌ %s", msg)
            result["error"] = msg
            return result

        if not user_config or not isinstance(user_config, dict):
            msg = (
                "user_config is required and must be a dictionary with at least "
                "'quasi_identifiers'."
            )
            logger.error("❌ %s", msg)
            result["error"] = msg
            return result

        try:
            normalized_aux = aux_df.copy()
            normalized_aux.columns = [_normalize_name(c) for c in normalized_aux.columns]

            normalized_anon = anon_df.copy()
            normalized_anon.columns = [_normalize_name(c) for c in normalized_anon.columns]

            normalized_config = self._normalize_user_config(user_config)

            result = self._process_user_mode(
                aux_df=normalized_aux,
                anon_df=normalized_anon,
                user_config=normalized_config,
            )
            self._save_configuration(result["final_config"])
            result["success"] = True
            logger.info("✅ Agent 2 processing completed successfully")

        except Exception as exc:
            logger.exception("❌ Agent 2 processing failed: %s", exc)
            result["error"] = str(exc)
            result["success"] = False

        logger.info("=" * 80)
        return result

    def _normalize_user_config(self, user_config: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(user_config)

        normalized["direct_identifiers"] = _normalize_name_list(
            user_config.get("direct_identifiers", [])
        )
        normalized["quasi_identifiers"] = _normalize_name_list(
            user_config.get("quasi_identifiers", [])
        )
        normalized["sensitive_attributes"] = _normalize_name_list(
            user_config.get("sensitive_attributes", [])
        )

        normalized["identifier_mapping"] = _normalize_mapping(
            user_config.get("identifier_mapping", {})
        )
        normalized["quasi_identifier_mapping"] = _normalize_mapping(
            user_config.get("quasi_identifier_mapping", {})
        )

        return normalized

    def _process_user_mode(
        self,
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
        user_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        logger.info("📋 Processing in USER mode")

        result: Dict[str, Any] = {
            "mode": "user",
            "validation": {},
            "mapping": {},
            "suggested_mappings": {},
            "final_config": {},
            "warnings": [],
        }

        # Step 1: validate direct identifiers
        if user_config.get("direct_identifiers"):
            logger.info("🔍 Validating user-provided direct_identifiers...")
            direct_validation = self.list_validator.validate_list(
                values=user_config["direct_identifiers"],
                df_auxiliary=aux_df,
                df_anonymized=anon_df,
                label="direct_identifiers",
                require_in_both=False,
            )
            result["validation"]["direct_identifiers"] = direct_validation
        else:
            result["validation"]["direct_identifiers"] = {
                "valid": [],
                "invalid": [],
                "warnings": ["⚠️ No direct_identifiers provided"],
                "suggestions": {},
                "is_valid": True,
            }

        # Step 2: validate quasi identifiers
        if user_config.get("quasi_identifiers"):
            logger.info("🔍 Validating user-provided quasi_identifiers...")
            qi_validation = self.list_validator.validate_list(
                values=user_config["quasi_identifiers"],
                df_auxiliary=aux_df,
                df_anonymized=anon_df,
                label="quasi_identifiers",
                require_in_both=True,
            )
            result["validation"]["quasi_identifiers"] = qi_validation

            if not qi_validation["is_valid"]:
                result["warnings"].append("Invalid columns in quasi_identifiers")
                for invalid_col in qi_validation["invalid"]:
                    suggestions = qi_validation["suggestions"].get(invalid_col, [])
                    if suggestions:
                        result["warnings"].append(
                            f"Column '{invalid_col}' not found. Did you mean: {suggestions}?"
                        )
        else:
            result["validation"]["quasi_identifiers"] = {
                "valid": [],
                "invalid": [],
                "warnings": ["❌ No quasi_identifiers provided"],
                "suggestions": {},
                "is_valid": False,
            }
            result["warnings"].append("No 'quasi_identifiers' key found in user_config.")

        # Step 3: validate sensitive attributes
        if user_config.get("sensitive_attributes"):
            logger.info("🔍 Validating user-provided sensitive_attributes...")
            sens_validation = self.list_validator.validate_list(
                values=user_config["sensitive_attributes"],
                df_auxiliary=aux_df,
                df_anonymized=anon_df,
                label="sensitive_attributes",
                require_in_both=False,
            )
            result["validation"]["sensitive_attributes"] = sens_validation
        else:
            result["validation"]["sensitive_attributes"] = {
                "valid": [],
                "invalid": [],
                "warnings": ["⚠️ No sensitive_attributes provided"],
                "suggestions": {},
                "is_valid": True,
            }

        # Step 4: validate explicit mappings
        if user_config.get("identifier_mapping") or user_config.get("quasi_identifier_mapping"):
            logger.info("🔗 Validating explicit column mappings...")
            mapping, invalid = self.mapper.map_columns_from_config(user_config, aux_df, anon_df)
            result["mapping"] = {
                "valid_mapping": mapping,
                "invalid_mapping": invalid,
            }
            if invalid:
                result["warnings"].append(f"{len(invalid)} invalid column mappings")
        else:
            result["mapping"] = {
                "valid_mapping": {},
                "invalid_mapping": [],
            }

        # Step 5: suggest value-based mappings for QI where names differ
        valid_qi = result["validation"]["quasi_identifiers"]["valid"]
        invalid_qi = result["validation"]["quasi_identifiers"]["invalid"]
        value_suggestions: Dict[str, List[Dict[str, Any]]] = {}

        if valid_qi:
            logger.info("🧠 Generating value-based mapping suggestions...")
            value_suggestions.update(self.mapping_suggester.suggest_mappings(
                aux_df=aux_df,
                anon_df=anon_df,
                candidate_columns=valid_qi,
            ))

        if invalid_qi:
            logger.info("🧠 Generating value-based mapping suggestions for unmatched quasi_identifiers...")
            value_suggestions.update(
                self._suggest_for_unmatched_quasi_identifiers(
                    aux_df=aux_df,
                    anon_df=anon_df,
                    invalid_quasi_identifiers=invalid_qi,
                    valid_quasi_identifiers=valid_qi,
                )
            )

        result["suggested_mappings"] = value_suggestions
        if value_suggestions:
            logger.info("💡 Value-based mapping suggestions found for %d column(s)", len(value_suggestions))

        # Step 6: build final config
        final_quasi_identifiers = list(valid_qi)
        for qi in result["suggested_mappings"].keys():
            if qi not in final_quasi_identifiers:
                final_quasi_identifiers.append(qi)

        result["final_config"] = {
            "direct_identifiers": result["validation"]["direct_identifiers"]["valid"],
            "quasi_identifiers": final_quasi_identifiers,
            "sensitive_attributes": result["validation"]["sensitive_attributes"]["valid"],
            "column_mapping": result["mapping"]["valid_mapping"],
            "suggested_mappings": result["suggested_mappings"],
            "source": "user_provided_upstream_component",
        }

        logger.info("📊 USER mode result:")
        logger.info("   Valid direct IDs    : %d", len(result["final_config"]["direct_identifiers"]))
        logger.info("   Valid QI            : %d", len(result["final_config"]["quasi_identifiers"]))
        logger.info("   Sensitive attrs     : %d", len(result["final_config"]["sensitive_attributes"]))
        logger.info("   Valid mappings      : %d", len(result["final_config"]["column_mapping"]))
        logger.info("   Suggested mappings  : %d", len(result["final_config"]["suggested_mappings"]))
        logger.info("   Warnings            : %d", len(result["warnings"]))

        return result

    def _suggest_for_unmatched_quasi_identifiers(
        self,
        aux_df: pd.DataFrame,
        anon_df: pd.DataFrame,
        invalid_quasi_identifiers: List[str],
        valid_quasi_identifiers: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Suggest mappings for quasi identifiers present in only one dataset.

        Example: auxiliary has 'district' while anonymized has 'city_name'.
        """
        suggestions: Dict[str, List[Dict[str, Any]]] = {}

        aux_cols = set(aux_df.columns)
        anon_cols = set(anon_df.columns)
        common_cols = aux_cols & anon_cols

        for col in invalid_quasi_identifiers:
            in_aux = col in aux_cols
            in_anon = col in anon_cols

            # Skip if column is present in neither dataset or already common.
            if in_aux == in_anon:
                continue

            source_is_aux = in_aux and not in_anon
            source_series = aux_df[col] if source_is_aux else anon_df[col]
            if not self.mapping_suggester._is_mapping_candidate(source_series):
                continue

            if source_is_aux:
                candidate_columns = [
                    c for c in anon_df.columns
                    if c not in common_cols and c not in valid_quasi_identifiers
                ]
            else:
                candidate_columns = [
                    c for c in aux_df.columns
                    if c not in common_cols and c not in valid_quasi_identifiers
                ]

            scored_matches: List[Dict[str, Any]] = []
            for candidate in candidate_columns:
                target_series = anon_df[candidate] if source_is_aux else aux_df[candidate]
                if not self.mapping_suggester._is_mapping_candidate(target_series):
                    continue

                overlap_score = self.mapping_suggester._value_overlap_ratio(source_series, target_series)
                if overlap_score >= self.mapping_suggester.overlap_threshold:
                    scored_matches.append(
                        {
                            "candidate": candidate,
                            "overlap_score": round(overlap_score, 4),
                            "reason": "high_value_overlap_unmatched_qi",
                        }
                    )

            if scored_matches:
                scored_matches.sort(key=lambda x: x["overlap_score"], reverse=True)
                suggestions[col] = scored_matches[: self.mapping_suggester.max_suggestions_per_column]

        return suggestions

    def _save_configuration(self, config: Dict[str, Any]) -> None:
        output_path = self.identifiers_dir / "identifier_classification.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        logger.info("💾 Configuration saved to: %s", output_path)


# Backward-compatible alias for older imports.
QIValidator = ColumnListValidator