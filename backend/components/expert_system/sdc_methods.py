"""
SDC Method Catalog for Expert System

Provides a structured registry of Statistical Disclosure Control (SDC) methods
with metadata: privacy level, utility impact, parameters, applicability, and
AI/agent feedback slots.

Used by the RecommendationEngine and KnowledgeBase to look up method details
when generating recommendations.
"""

from typing import Dict, List, Any, Optional
from .models import SDCMethod


class SDCMethodCatalog:
    """
    Registry of all supported Statistical Disclosure Control methods.

    Each entry is an SDCMethod dataclass carrying:
    - key          : unique identifier used throughout the system
    - label        : human-readable name
    - description  : one-sentence summary
    - privacy_level: Low / Medium / High / Very High
    - utility_impact: Low / Medium / High / Very High
    - parameters   : dict of configurable parameters with defaults
    - applicable_to: list of data types the method applies to
    - ai_feedback  : slot for runtime agent notes (None by default)
    """

    def __init__(self):
        self._methods: Dict[str, SDCMethod] = {}
        self._register_all()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_method(self, key: str) -> Optional[SDCMethod]:
        """Return the SDCMethod for *key*, or None if not found."""
        return self._methods.get(key)

    def get_all_methods(self) -> Dict[str, SDCMethod]:
        """Return the full method registry."""
        return dict(self._methods)

    def update_ai_feedback(self, key: str, feedback: str) -> None:
        """Attach AI-agent feedback to a method (mutates in place)."""
        if key in self._methods:
            self._methods[key].ai_feedback = feedback

    # ------------------------------------------------------------------
    # Internal registration
    # ------------------------------------------------------------------

    def _register(self, method: SDCMethod) -> None:
        self._methods[method.key] = method

    def _register_all(self) -> None:
        # â”€â”€ Microdata protection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._register(SDCMethod(
            key="k_anonymity",
            label="K-Anonymity",
            description="Ensure every record is indistinguishable from at least k-1 others on QI values.",
            privacy_level="High",
            utility_impact="Medium",
            parameters={"k": 5},
            applicable_to=["categorical", "numeric", "datetime"],
        ))
        self._register(SDCMethod(
            key="l_diversity",
            label="L-Diversity",
            description="Extend k-anonymity so each equivalence class contains at least l distinct sensitive values.",
            privacy_level="High",
            utility_impact="Medium",
            parameters={"k": 5, "l": 2},
            applicable_to=["categorical", "numeric"],
        ))
        self._register(SDCMethod(
            key="t_closeness",
            label="T-Closeness",
            description="Require the distribution of sensitive values in each group to be within distance t of the overall distribution.",
            privacy_level="Very High",
            utility_impact="High",
            parameters={"k": 5, "t": 0.2},
            applicable_to=["categorical", "numeric"],
        ))

        # â”€â”€ Transformation / generalisation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._register(SDCMethod(
            key="generalization",
            label="Generalization",
            description="Replace specific values with broader categories (e.g. exact age â†’ age range).",
            privacy_level="Medium",
            utility_impact="Medium",
            parameters={"bins": 5, "method": "numeric_binning"},
            applicable_to=["numeric", "categorical", "datetime", "geographic"],
        ))
        self._register(SDCMethod(
            key="suppression",
            label="Suppression",
            description="Remove or mask rare / outlier values that are highly identifying.",
            privacy_level="High",
            utility_impact="High",
            parameters={"threshold": 5},
            applicable_to=["categorical", "numeric"],
        ))
        self._register(SDCMethod(
            key="local_suppression",
            label="Local Suppression",
            description="Suppress individual cells (not whole records) that create small equivalence classes.",
            privacy_level="High",
            utility_impact="Medium",
            parameters={"max_suppression_per_column": 0.1},
            applicable_to=["categorical", "numeric"],
        ))
        self._register(SDCMethod(
            key="microaggregation",
            label="Microaggregation",
            description="Replace individual values with group means/medians computed over small clusters.",
            privacy_level="High",
            utility_impact="Medium",
            parameters={"k": 3},
            applicable_to=["numeric"],
        ))
        self._register(SDCMethod(
            key="top_bottom_coding",
            label="Top/Bottom Coding",
            description="Cap extreme values at configurable thresholds to reduce outlier disclosure risk.",
            privacy_level="Medium",
            utility_impact="Low",
            parameters={"percentile_low": 5, "percentile_high": 95},
            applicable_to=["numeric"],
        ))
        self._register(SDCMethod(
            key="perturbation",
            label="Noise Perturbation",
            description="Add calibrated random noise to numeric attributes to mask precise values.",
            privacy_level="Medium",
            utility_impact="Medium",
            parameters={"noise_level": 0.05},
            applicable_to=["numeric"],
        ))
        self._register(SDCMethod(
            key="data_swapping",
            label="Data Swapping",
            description="Swap attribute values between records to break direct linkages while preserving marginals.",
            privacy_level="Medium",
            utility_impact="Low",
            parameters={"swap_rate": 0.1},
            applicable_to=["categorical", "numeric"],
        ))
        self._register(SDCMethod(
            key="pram",
            label="PRAM (Post-Randomisation Method)",
            description="Randomly recode categorical values according to a transition matrix, preserving overall distribution.",
            privacy_level="High",
            utility_impact="Medium",
            parameters={"perturbation_rate": 0.05, "seed": 42},
            applicable_to=["categorical"],
        ))
        self._register(SDCMethod(
            key="bucketization",
            label="Bucketization",
            description="Bin numeric columns into equal-width or equal-frequency buckets, preserving distribution shape.",
            privacy_level="Medium",
            utility_impact="Low",
            parameters={"n_buckets": 10},
            applicable_to=["numeric"],
        ))
        self._register(SDCMethod(
            key="hashing",
            label="Hashing / Pseudonymisation",
            description="Replace direct identifiers with cryptographic hashes or pseudonyms.",
            privacy_level="Very High",
            utility_impact="Low",
            parameters={"algorithm": "sha256"},
            applicable_to=["categorical"],
        ))
        self._register(SDCMethod(
            key="attribute_suppression",
            label="Attribute Suppression",
            description="Remove an entire column that is too identifying or not necessary for the release.",
            privacy_level="Very High",
            utility_impact="High",
            parameters={},
            applicable_to=["categorical", "numeric", "datetime", "geographic"],
        ))

        # â”€â”€ Geographic / census-specific â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._register(SDCMethod(
            key="psu_aggregation",
            label="PSU Aggregation/Recoding",
            description="Aggregate PSU to district/region level OR randomly re-code with minimum group size enforcement (k>=5).",
            privacy_level="Very High",
            utility_impact="Medium",
            parameters={"min_group_size": 5},
            applicable_to=["geographic", "categorical"],
        ))
        self._register(SDCMethod(
            key="geo_generalization",
            label="Geographic Generalization",
            description="Generalise geographic identifiers to a coarser administrative level (e.g. exact address â†’ district).",
            privacy_level="High",
            utility_impact="Medium",
            parameters={"level": "district"},
            applicable_to=["geographic"],
        ))
        self._register(SDCMethod(
            key="spatial_cloaking",
            label="Spatial Cloaking",
            description="Replace precise coordinates with a bounding region that contains at least k individuals.",
            privacy_level="High",
            utility_impact="Medium",
            parameters={"k": 5},
            applicable_to=["geographic"],
        ))
        self._register(SDCMethod(
            key="household_aggregation",
            label="Household Aggregation",
            description="Aggregate individual-level records to household level to reduce combinatorial risk.",
            privacy_level="High",
            utility_impact="Medium",
            parameters={},
            applicable_to=["categorical", "numeric"],
        ))
        self._register(SDCMethod(
            key="temporal_generalization",
            label="Temporal Generalization",
            description="Coarsen date/time values to week, month, or year ranges to reduce temporal re-identification.",
            privacy_level="Medium",
            utility_impact="Low",
            parameters={"granularity": "month"},
            applicable_to=["datetime"],
        ))

        # â”€â”€ Dimensionality / feature reduction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._register(SDCMethod(
            key="feature_selection",
            label="Feature Selection / QI Reduction",
            description="Drop highly correlated or redundant quasi-identifiers to reduce the dimensionality of the risk space.",
            privacy_level="Medium",
            utility_impact="Medium",
            parameters={"correlation_threshold": 0.7},
            applicable_to=["categorical", "numeric"],
        ))
        self._register(SDCMethod(
            key="dimensionality_reduction",
            label="Dimensionality Reduction",
            description="Apply PCA or similar to collapse high-dimensional QI space before release.",
            privacy_level="Medium",
            utility_impact="Medium",
            parameters={"n_components": 3},
            applicable_to=["numeric"],
        ))

        # â”€â”€ Advanced / policy-driven â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._register(SDCMethod(
            key="differential_privacy",
            label="Differential Privacy",
            description="Add mathematically calibrated noise guaranteeing Îµ-differential privacy for all queries.",
            privacy_level="Very High",
            utility_impact="High",
            parameters={"epsilon": 1.0, "sensitivity": 1.0},
            applicable_to=["numeric", "categorical"],
        ))
        self._register(SDCMethod(
            key="synthetic_data",
            label="Synthetic Data Generation",
            description="Replace the original dataset with a statistically representative synthetic dataset with no real records.",
            privacy_level="Very High",
            utility_impact="Medium",
            parameters={"method": "ctgan"},
            applicable_to=["categorical", "numeric", "datetime"],
        ))
        self._register(SDCMethod(
            key="sampling",
            label="Sampling",
            description="Release only a random sample of records to reduce disclosure risk while preserving aggregate statistics.",
            privacy_level="Medium",
            utility_impact="Low",
            parameters={"sample_fraction": 0.1},
            applicable_to=["categorical", "numeric", "datetime", "geographic"],
        ))
        self._register(SDCMethod(
            key="hybrid",
            label="Hybrid Approach",
            description="Apply a layered combination of complementary SDC methods for datasets with multiple high-risk characteristics.",
            privacy_level="Very High",
            utility_impact="High",
            parameters={},
            applicable_to=["categorical", "numeric", "datetime", "geographic"],
        ))
            
