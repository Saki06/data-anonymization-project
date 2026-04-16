"""
Rule engine for expert system - defines and evaluates rules based on profile metrics
"""

from typing import List, Dict, Any
from .models import Rule


class RulesEngine:
    """Manages rules and evaluates them against profile data."""

    def __init__(self):
        self.rules: List[Rule] = self._initialize_rules()

    def _initialize_rules(self) -> List[Rule]:
        """Initialize all expert system rules."""
        return [
            # === High Cardinality Risks ===
            Rule(
                name="High Cardinality in QI",
                conditions=[lambda p: p.get('unique_ratio', 0) > 0.9],
                recommended_methods=["generalization", "suppression"],
                explanation="QI columns have >90% unique values; generalization or suppression reduces re-ID risk.",
                severity="High"
            ),
            Rule(
                name="Continuous Numeric QIs",
                conditions=[lambda p: p.get('num_continuous_qi', 0) > 0],
                recommended_methods=["generalization", "microaggregation", "top_bottom_coding"],
                explanation="Numeric QIs with high precision; binning/generalization recommended.",
                severity="High"
            ),

            # === Sensitive Attribute Risks ===
            Rule(
                name="Low Diversity in Sensitive Attribute",
                conditions=[lambda p: p.get('sensitive_distinct', 100) < 3],
                recommended_methods=["l_diversity", "t_closeness", "differential_privacy"],
                explanation="Sensitive attribute has <3 distinct values; l-diversity or t-closeness needed.",
                severity="High"
            ),
            Rule(
                name="Skewed Sensitive Distribution",
                conditions=[lambda p: p.get('sensitive_max_freq', 0) > 0.5],
                recommended_methods=["t_closeness", "differential_privacy"],
                explanation="Sensitive attribute is highly skewed (>50% one value); t-closeness recommended.",
                severity="High"
            ),

            # === Equivalence Class Risks ===
            Rule(
                name="Small Equivalence Classes",
                conditions=[lambda p: p.get('min_group_size', 100) < p.get('k_threshold', 5)],
                recommended_methods=["k_anonymity", "microaggregation", "generalization"],
                explanation="Some equivalence classes are too small; k-anonymity or generalization required.",
                severity="High"
            ),
            Rule(
                name="Rare QI Combinations",
                conditions=[lambda p: p.get('rare_combinations_ratio', 0) > 0.1],
                recommended_methods=["suppression", "generalization", "microaggregation"],
                explanation=">10% of records have rare QI combinations; suppression or generalization needed.",
                severity="High"
            ),

            # === Correlation & Dimensionality Risks ===
            Rule(
                name="High QI Correlation",
                conditions=[lambda p: p.get('max_qi_correlation', 0) > 0.7],
                recommended_methods=["feature_selection", "generalization"],
                explanation="QI columns are highly correlated (>0.7); feature selection may reduce redundancy.",
                severity="Medium"
            ),
            Rule(
                name="High Dimensionality (Many QIs)",
                conditions=[lambda p: p.get('num_qi', 0) > 5],
                recommended_methods=["feature_selection", "dimensionality_reduction"],
                explanation=">5 QI columns; dimensionality reduction or feature selection recommended.",
                severity="Medium"
            ),

            # === Numeric & Outlier Risks ===
            Rule(
                name="Numeric QI Outliers",
                conditions=[lambda p: p.get('outliers_detected', False)],
                recommended_methods=["microaggregation", "top_bottom_coding", "generalization"],
                explanation="Outliers detected in numeric QIs; microaggregation or top/bottom coding recommended.",
                severity="Medium"
            ),

            # === Census-Specific Risks ===
            Rule(
                name="PSU Detected at Release Level",
                conditions=[lambda p: p.get('has_psu', False) and p.get('psu_at_release', False)],
                recommended_methods=["psu_aggregation", "geo_generalization"],
                explanation="PSU at release level enables re-ID; must aggregate or generalize geographically.",
                severity="Critical"
            ),
            Rule(
                name="Geographic Precision Risk",
                conditions=[lambda p: p.get('has_geographic_qi', False) and p.get('geographic_precision', 'district') == 'exact'],
                recommended_methods=["geo_generalization", "spatial_cloaking"],
                explanation="Exact geographic data is highly identifying; must generalize.",
                severity="High"
            ),
            Rule(
                name="Household Hierarchical Data",
                conditions=[lambda p: p.get('is_household_data', False)],
                recommended_methods=["household_aggregation", "psu_aggregation"],
                explanation="Household survey data detected; household-level aggregation may be appropriate.",
                severity="Medium"
            ),

            # === Temporal Risks ===
            Rule(
                name="Temporal Patterns Detected",
                conditions=[lambda p: p.get('has_temporal_qi', False) and p.get('temporal_patterns', False)],
                recommended_methods=["temporal_generalization", "perturbation"],
                explanation="Time-based patterns detected; temporal generalization recommended.",
                severity="Medium"
            ),

            # === Linkage Attack Risks ===
            Rule(
                name="Unique Records (Row Linkage Risk)",
                conditions=[lambda p: p.get('unique_records_ratio', 0) > 0.05],
                recommended_methods=["suppression", "generalization", "data_swapping"],
                explanation=">5% unique records (vulnerable to row linkage); suppression or generalization needed.",
                severity="High"
            ),

            # === Advanced / Policy-Driven Rules ===
            Rule(
                name="Differential Privacy Required",
                conditions=[lambda p: p.get('dp_required', False)],
                recommended_methods=["differential_privacy"],
                explanation="Differential privacy required by policy or user preferences.",
                severity="High"
            ),
            Rule(
                name="Synthetic Data Appropriate",
                conditions=[lambda p: p.get('synthetic_suitable', False)],
                recommended_methods=["synthetic_data"],
                explanation="Complete data synthesis suitable for this dataset's characteristics.",
                severity="Medium"
            ),

            # === Multiple High-Risk Conditions ===
            Rule(
                name="Multiple High-Risk Conditions",
                conditions=[lambda p: p.get('num_high_risk', 0) >= 3],
                recommended_methods=["hybrid"],
                explanation="Multiple high-risk issues detected; hybrid approach with layered protection recommended.",
                severity="Critical"
            ),
            # === Newly added rules for expanded SDC methods ===
            Rule(
                name="PRAM Suitable",
                conditions=[
                    lambda p: (p.get('categorical_risk_score', 0) > 0.3 or p.get('has_categorical_qi', False)) and not p.get('dp_required', False)
                ],
                recommended_methods=["pram", "generalization", "suppression"],
                explanation="Categorical quasi-identifiers detected; PRAM can mask values while preserving distribution.",
                severity="High"
            ),
            Rule(
                name="Local Suppression Opportunity",
                conditions=[
                    lambda p: p.get('rare_values_ratio', 0) > 0.05
                ],
                recommended_methods=["local_suppression", "suppression"],
                explanation="Several rare values present; local suppression can target specific cells.",
                severity="High"
            ),
            Rule(
                name="Bucketization Recommended",
                conditions=[
                    lambda p: p.get('num_continuous_qi', 0) > 0 and p.get('high_cardinality_numeric', False)
                ],
                recommended_methods=["bucketization", "generalization"],
                explanation="Numeric QIs with high cardinality; bucketization will preserve distribution boundaries.",
                severity="Medium"
            ),
            Rule(
                name="Sampling Suitable",
                conditions=[
                    lambda p: p.get('dataset_size', 0) > 100000 and p.get('sampling_allowed', True)
                ],
                recommended_methods=["sampling"],
                explanation="Large dataset size; sampling reduces disclosure risk with minimal utility loss.",
                severity="Medium"
            ),
            Rule(
                name="Identifiers Present",
                conditions=[
                    lambda p: p.get('identifier_present', False)
                ],
                recommended_methods=["hashing", "attribute_suppression"],
                explanation="Identifying attributes found; hash or suppress identifiers before release.",
                severity="High"
            ),
        ]

    def evaluate_profile(self, profile: Dict[str, Any]) -> List[str]:
        """
        Evaluate profile against all rules.
        Returns list of triggered rule names.
        """
        triggered_rules = []
        for rule in self.rules:
            if all(cond(profile) for cond in rule.conditions):
                triggered_rules.append(rule.name)
        return triggered_rules

    def get_recommendations_for_profile(self, profile: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Evaluate profile and return recommended methods per triggered rule.
        Returns dict: {rule_name: [method_keys, ...]}
        """
        recommendations = {}
        for rule in self.rules:
            if all(cond(profile) for cond in rule.conditions):
                recommendations[rule.name] = rule.recommended_methods
        return recommendations

    def get_rule_details(self, rule_name: str) -> Rule:
        """Get detailed information about a specific rule."""
        for rule in self.rules:
            if rule.name == rule_name:
                return rule
        return None

    def add_custom_rule(self, rule: Rule):
        """Add a custom rule to the engine."""
        self.rules.append(rule)

    def get_all_rules(self) -> List[Rule]:
        """Get all rules."""
        return self.rules