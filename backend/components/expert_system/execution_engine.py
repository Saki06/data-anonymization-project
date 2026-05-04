"""
Anonymization Execution Engine
Converts recommendations into enforced privacy constraints.

This engine bridges the gap between advisory recommendations and actual
enforcement by:
1. Executing recommended transformations
2. Validating privacy constraints after transformation
3. Iterating/adaptively refining when violations occur

Workflow:
    recommend methods
            ↓
    execute transformations
            ↓
    validate k-anonymity
            ↓
    if violation → iterate with adapted parameters
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import logging

# Import from sibling modules
from .models import RecommendationSet, Recommendation
from ..anonymization.methods import AnonymizationMethods

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of executing anonymization with validation."""
    success: bool
    anonymized_data: Optional[pd.DataFrame] = None
    original_data: Optional[pd.DataFrame] = None
    applied_methods: List[str] = field(default_factory=list)
    parameters_used: Dict[str, Any] = field(default_factory=dict)
    validation_results: Dict[str, Any] = field(default_factory=dict)
    violations: List[Dict[str, Any]] = field(default_factory=list)
    iterations_performed: int = 0
    final_k_value: Optional[int] = None
    final_l_value: Optional[int] = None
    final_t_value: Optional[float] = None
    suppression_ratio: float = 0.0
    error_message: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validating privacy constraints."""
    is_valid: bool
    constraint_type: str
    actual_value: Any
    required_value: Any
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


class AnonymizationExecutionEngine:
    """
    Execution Engine that enforces privacy constraints.
    
    This is the core component that transforms the system from an
    advisory tool into an enforcement engine.
    """

    def __init__(self, max_iterations: int = 5):
        """
        Initialize the execution engine.
        
        Args:
            max_iterations: Maximum iterations for constraint satisfaction
        """
        self.max_iterations = max_iterations
        self.methods = AnonymizationMethods()
        
    def execute_with_validation(
        self,
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        recommendations: RecommendationSet,
        initial_params: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Execute recommended methods with full validation and iteration.
        
        This is the main entry point that:
        1. Executes recommended transformations
        2. Validates constraints
        3. Iterates if violations occur
        
        Args:
            df: Original dataframe
            quasi_identifiers: List of QI column names
            sensitive_attributes: List of sensitive attribute names
            recommendations: RecommendationSet from the expert system
            initial_params: Optional initial parameters (k, l, t, etc.)
            
        Returns:
            ExecutionResult with validation status and anonymized data
        """
        # Initialize parameters
        params = initial_params or {}
        k = int(params.get('k', 5))
        l = int(params.get('l', 2))
        t = float(params.get('t', 0.2))
        generalization_level = float(params.get('generalization_level', 0.5))
        generalization_strategy = str(params.get('generalization_strategy', 'traditional')).lower()
        max_hierarchy_level = int(params.get('max_hierarchy_level', 4))
        forced_primary_method = params.get("forced_primary_method")
        
        # Track iterations
        iteration = 0
        violations = []
        
        # Work on a copy
        anon_df = df.copy()
        applied_methods = []
        
        logger.info(f"Starting execution with k={k}, l={l}, t={t}")
        
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"Execution iteration {iteration}/{self.max_iterations}")
            
            # Reset to original for re-execution
            anon_df = df.copy()
            applied_methods = []
            
            # Step 1: Handle PSU if present (from recommendations or detection)
            psu_columns = self._detect_psu_columns(df, quasi_identifiers)
            for psu_col in psu_columns:
                anon_df = self.methods.handle_psu(anon_df, psu_col, method='random_recode')
                applied_methods.append(f"psu_handling_{psu_col}")
            
            # Step 2: Apply generalization based on recommendation
            if generalization_level > 0 and generalization_strategy != "hierarchy":
                for qi in quasi_identifiers:
                    if qi in anon_df.columns:
                        if pd.api.types.is_numeric_dtype(anon_df[qi]):
                            anon_df = self.methods.generalization(
                                anon_df, qi, method='numeric_binning', 
                                bins=max(2, int(10 * (1 - generalization_level) + 2))
                            )
                        else:
                            anon_df = self.methods.generalization(
                                anon_df, qi, method='suppress_rare'
                            )
                applied_methods.append("generalization")
            
            # Step 3: Apply primary recommended method
            primary_method_source = forced_primary_method or recommendations.primary_method
            primary_method = str(primary_method_source).lower().replace('-', '_').replace(' ', '_')
            
            if 'k_anonymity' in primary_method or 'k-anonymity' in primary_method:
                if generalization_strategy == "hierarchy":
                    anon_df, info = self.methods.k_anonymity_with_hierarchy(
                        anon_df, quasi_identifiers, k=k, max_hierarchy_level=max_hierarchy_level
                    )
                    applied_methods.append(f"k_anonymity_hierarchy_k{k}")
                    applied_methods.append(f"hierarchy_iterations_{info.get('iterations', 0)}")
                else:
                    anon_df = self.methods.k_anonymity(anon_df, quasi_identifiers, k=k)
                    applied_methods.append(f"k_anonymity_k{k}")
                
            elif 'l_diversity' in primary_method or 'l-diversity' in primary_method:
                # First apply k-anonymity, then l-diversity
                if generalization_strategy == "hierarchy":
                    anon_df, _ = self.methods.k_anonymity_with_hierarchy(
                        anon_df, quasi_identifiers, k=k, max_hierarchy_level=max_hierarchy_level
                    )
                else:
                    anon_df = self.methods.k_anonymity(anon_df, quasi_identifiers, k=k)
                for sens_attr in sensitive_attributes:
                    if sens_attr in anon_df.columns:
                        anon_df = self.methods.l_diversity(
                            anon_df, quasi_identifiers, sens_attr, l=l
                        )
                applied_methods.append(f"l_diversity_l{l}")
                
            elif 't_closeness' in primary_method or 't-closeness' in primary_method:
                if generalization_strategy == "hierarchy":
                    anon_df, _ = self.methods.k_anonymity_with_hierarchy(
                        anon_df, quasi_identifiers, k=k, max_hierarchy_level=max_hierarchy_level
                    )
                else:
                    anon_df = self.methods.k_anonymity(anon_df, quasi_identifiers, k=k)
                for sens_attr in sensitive_attributes:
                    if sens_attr in anon_df.columns:
                        anon_df = self.methods.t_closeness(
                            anon_df, quasi_identifiers, sens_attr, t=t
                        )
                applied_methods.append(f"t_closeness_t{t}")
                
            elif 'hybrid' in primary_method:
                anon_df = self.methods.apply_hybrid_anonymization(
                    anon_df, quasi_identifiers, sensitive_attributes,
                    k=k, l=l, t=t
                )
                applied_methods.append("hybrid_anonymization")
                
            elif 'pram' in primary_method:
                # PRAM (Post-Randomisation Method) for categorical variables
                # Get perturbation rate from params (default 0.1 for 10% perturbation)
                perturbation_rate = float(params.get('perturbation_rate', 0.05))
                
                # Apply PRAM to categorical quasi-identifiers
                categorical_qis = []
                for qi in quasi_identifiers:
                    if qi in anon_df.columns:
                        # Check if column is categorical (not numeric)
                        if not pd.api.types.is_numeric_dtype(anon_df[qi]):
                            categorical_qis.append(qi)
                
                if categorical_qis:
                    anon_df = self.methods.pram(
                        anon_df, 
                        categorical_qis, 
                        perturbation_rate=perturbation_rate,
                        seed=params.get('seed', 42)
                    )
                    applied_methods.append(f"pram_perturbation_{int(perturbation_rate*100)}%")
                else:
                    # Fallback to k-anonymity if no categorical columns
                    anon_df, _ = self.methods.k_anonymity_with_hierarchy(
                        anon_df, quasi_identifiers, k=k, max_hierarchy_level=max_hierarchy_level
                    )
                    applied_methods.append(f"k_anonymity_hierarchy_k{k}_fallback")
            
            else:
                # Default: apply k-anonymity
                if generalization_strategy == "hierarchy":
                    anon_df, _ = self.methods.k_anonymity_with_hierarchy(
                        anon_df, quasi_identifiers, k=k, max_hierarchy_level=max_hierarchy_level
                    )
                    applied_methods.append(f"k_anonymity_hierarchy_k{k}")
                else:
                    anon_df = self.methods.k_anonymity(anon_df, quasi_identifiers, k=k)
                    applied_methods.append(f"k_anonymity_k{k}")
            
            # Step 3.5: Apply microaggregation to numeric sensitive attributes
            # This ensures numeric sensitive attributes like income are properly anonymized
            for sens_attr in sensitive_attributes:
                if sens_attr in anon_df.columns and sens_attr not in quasi_identifiers:
                    if pd.api.types.is_numeric_dtype(anon_df[sens_attr]):
                        try:
                            # Apply microaggregation with group size proportional to dataset size
                            group_size = max(3, len(anon_df) // 100)
                            anon_df = self.methods.microaggregation(anon_df, sens_attr, group_size=group_size)
                            applied_methods.append(f"microaggregation_{sens_attr}_group{group_size}")
                            logger.info(f"Applied microaggregation to {sens_attr} with group_size={group_size}")
                        except Exception as e:
                            logger.warning(f"Could not apply microaggregation to {sens_attr}: {e}")
            
            # Step 4: Validate constraints
            validation_results = self._validate_constraints(
                anon_df, df, quasi_identifiers, sensitive_attributes,
                k=k, l=l, t=t
            )
            
            # Check if all constraints are satisfied
            all_valid = all(v.is_valid for v in validation_results.values())
            
            if all_valid:
                logger.info(f"All constraints satisfied after {iteration} iteration(s)")
                break
            
            # Collect violations
            for constraint_name, result in validation_results.items():
                if not result.is_valid:
                    violations.append({
                        "iteration": iteration,
                        "constraint": constraint_name,
                        "actual": result.actual_value,
                        "required": result.required_value,
                        "message": result.message
                    })
            
            # Step 5: Adapt parameters if not satisfied
            if iteration < self.max_iterations:
                # Increase k or generalization level to satisfy constraints
                k_adjusted = False
                gen_adjusted = False
                
                for constraint_name, result in validation_results.items():
                    if not result.is_valid:
                        if 'k-anonymity' in constraint_name and result.actual_value < result.required_value:
                            # Increase k
                            k = min(k + 1, 15)  # Cap at 15
                            k_adjusted = True
                        elif 'generalization' in constraint_name or 'suppression' in constraint_name:
                            # Increase generalization
                            generalization_level = min(generalization_level + 0.1, 0.9)
                            gen_adjusted = True
                
                logger.info(f"Adapting parameters: k={k}, gen={generalization_level}")
        
        # Calculate final metrics
        suppression_ratio = self._calculate_suppression_ratio(anon_df, quasi_identifiers)
        
        # Build final validation results dict
        validation_dict = {}
        for constraint_name, result in validation_results.items():
            validation_dict[constraint_name] = {
                "is_valid": result.is_valid,
                "actual_value": result.actual_value,
                "required_value": result.required_value,
                "message": result.message,
                "details": result.details
            }
        
        return ExecutionResult(
            success=len(violations) == 0 or iteration > 0,
            anonymized_data=anon_df,
            original_data=df,
            applied_methods=applied_methods,
            parameters_used={
                "k": k,
                "l": l,
                "t": t,
                "generalization_level": generalization_level
            },
            validation_results=validation_dict,
            violations=violations,
            iterations_performed=iteration,
            final_k_value=k,
            final_l_value=l,
            final_t_value=t,
            suppression_ratio=suppression_ratio
        )

    def _detect_psu_columns(self, df: pd.DataFrame, quasi_identifiers: List[str]) -> List[str]:
        """Detect potential PSU (Primary Sampling Unit) columns."""
        psu_columns = []
        psu_keywords = ['psu', 'sampling_unit', 'cluster', 'household_id', 'family_id']
        
        for col in df.columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in psu_keywords):
                psu_columns.append(col)
            # Also check if column has very high cardinality and is in QI list
            elif col in quasi_identifiers:
                unique_ratio = df[col].nunique() / len(df)
                if unique_ratio > 0.8:  # Very high uniqueness
                    # Check if it's not a direct identifier but could be PSU-like
                    if any(keyword in col_lower for keyword in ['id', 'code', 'number']):
                        psu_columns.append(col)
        
        return psu_columns

    def _validate_constraints(
        self,
        anon_df: pd.DataFrame,
        original_df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        k: int,
        l: int,
        t: float
    ) -> Dict[str, ValidationResult]:
        """
        Validate all privacy constraints.
        
        Returns dict mapping constraint names to ValidationResults.
        """
        results = {}
        
        # 1. Validate k-anonymity
        k_result = self._validate_k_anonymity(anon_df, quasi_identifiers, k)
        results['k-anonymity'] = k_result
        
        # 2. Validate l-diversity for each sensitive attribute
        for sens_attr in sensitive_attributes:
            if sens_attr in anon_df.columns:
                l_result = self._validate_l_diversity(anon_df, quasi_identifiers, sens_attr, l)
                results[f'l-diversity-{sens_attr}'] = l_result
        
        # 3. Validate t-closeness for each sensitive attribute
        for sens_attr in sensitive_attributes:
            if sens_attr in anon_df.columns:
                t_result = self._validate_t_closeness(anon_df, original_df, quasi_identifiers, sens_attr, t)
                results[f't-closeness-{sens_attr}'] = t_result
        
        return results

    def _validate_k_anonymity(
        self, 
        df: pd.DataFrame, 
        quasi_identifiers: List[str], 
        required_k: int
    ) -> ValidationResult:
        """Validate k-anonymity constraint."""
        if not quasi_identifiers:
            return ValidationResult(
                is_valid=True,
                constraint_type="k-anonymity",
                actual_value=None,
                required_value=required_k,
                message="No quasi-identifiers to validate"
            )
        
        existing_qis = [qi for qi in quasi_identifiers if qi in df.columns]
        if not existing_qis:
            return ValidationResult(
                is_valid=False,
                constraint_type="k-anonymity",
                actual_value=0,
                required_value=required_k,
                message="No valid quasi-identifiers found"
            )
        
        try:
            qi_df = df[existing_qis]
            groups = qi_df.groupby(list(existing_qis)).size()
            min_group_size = int(groups.min()) if len(groups) > 0 else 0
            
            is_valid = min_group_size >= required_k
            
            # Calculate details
            group_sizes = groups.tolist()
            avg_size = float(groups.mean()) if len(groups) > 0 else 0
            total_groups = len(groups)
            compliant_groups = sum(1 for size in group_sizes if size >= required_k)
            
            return ValidationResult(
                is_valid=is_valid,
                constraint_type="k-anonymity",
                actual_value=min_group_size,
                required_value=required_k,
                message=f"Min group size: {min_group_size}, Required: {required_k}",
                details={
                    "min_group_size": min_group_size,
                    "avg_group_size": round(avg_size, 2),
                    "total_groups": total_groups,
                    "compliant_groups": compliant_groups,
                    "compliance_rate": round(compliant_groups / total_groups * 100, 2) if total_groups > 0 else 0
                }
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                constraint_type="k-anonymity",
                actual_value=0,
                required_value=required_k,
                message=f"Validation error: {str(e)}"
            )

    def _validate_l_diversity(
        self,
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attribute: str,
        required_l: int
    ) -> ValidationResult:
        """Validate l-diversity constraint."""
        if not quasi_identifiers or sensitive_attribute not in df.columns:
            return ValidationResult(
                is_valid=True,
                constraint_type="l-diversity",
                actual_value=None,
                required_value=required_l,
                message="No valid attributes for l-diversity validation"
            )
        
        existing_qis = [qi for qi in quasi_identifiers if qi in df.columns]
        if not existing_qis:
            return ValidationResult(
                is_valid=False,
                constraint_type="l-diversity",
                actual_value=0,
                required_value=required_l,
                message="No valid quasi-identifiers"
            )
        
        try:
            groups = df.groupby(list(existing_qis))
            min_diversity = float('inf')
            # Keep details bounded; large dicts slow responses for real microdata
            details = {"examples": []}
            
            for group_key, idx in groups.groups.items():
                group_data = df.loc[idx]
                distinct_count = int(group_data[sensitive_attribute].nunique())
                min_diversity = min(min_diversity, distinct_count)
                if len(details["examples"]) < 10:
                    details["examples"].append({"group": str(group_key), "distinct": distinct_count})
            
            if min_diversity == float('inf'):
                min_diversity = 0
            
            is_valid = min_diversity >= required_l
            
            return ValidationResult(
                is_valid=is_valid,
                constraint_type="l-diversity",
                actual_value=min_diversity,
                required_value=required_l,
                message=f"Min diversity: {min_diversity}, Required: {required_l}",
                details=details
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                constraint_type="l-diversity",
                actual_value=0,
                required_value=required_l,
                message=f"Validation error: {str(e)}"
            )

    def _validate_t_closeness(
        self,
        anon_df: pd.DataFrame,
        original_df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attribute: str,
        required_t: float
    ) -> ValidationResult:
        """Validate t-closeness constraint."""
        if not quasi_identifiers or sensitive_attribute not in anon_df.columns:
            return ValidationResult(
                is_valid=True,
                constraint_type="t-closeness",
                actual_value=None,
                required_value=required_t,
                message="No valid attributes for t-closeness validation"
            )
        
        existing_qis = [qi for qi in quasi_identifiers if qi in anon_df.columns]
        if not existing_qis:
            return ValidationResult(
                is_valid=False,
                constraint_type="t-closeness",
                actual_value=1.0,
                required_value=required_t,
                message="No valid quasi-identifiers"
            )
        
        try:
            # Calculate global distribution
            global_dist = original_df[sensitive_attribute].value_counts(normalize=True).to_dict()
            is_ordinal = self.methods._is_ordinal_attribute(original_df, sensitive_attribute)
            
            # Check max distance across all groups
            groups = anon_df.groupby(list(existing_qis))
            max_distance = 0.0
            details = {"examples": []}
            
            for group_key, group_indices in groups.groups.items():
                group_data = anon_df.loc[group_indices]
                local_dist = group_data[sensitive_attribute].value_counts(normalize=True).to_dict()

                # Calculate TVD (categorical) or EMD-like (ordinal/numeric) using the shared method helper.
                distance = float(self.methods._calculate_distribution_distance(
                    local_dist, global_dist, is_ordinal=is_ordinal
                ))
                max_distance = max(max_distance, distance)
                if len(details["examples"]) < 10:
                    details["examples"].append({"group": str(group_key), "distance": round(distance, 4)})
            
            is_valid = max_distance <= required_t
            
            return ValidationResult(
                is_valid=is_valid,
                constraint_type="t-closeness",
                actual_value=round(max_distance, 4),
                required_value=required_t,
                message=f"Max distance: {max_distance:.4f}, Required: {required_t}",
                details=details
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                constraint_type="t-closeness",
                actual_value=1.0,
                required_value=required_t,
                message=f"Validation error: {str(e)}"
            )

    def _calculate_suppression_ratio(
        self, 
        anon_df: pd.DataFrame, 
        quasi_identifiers: List[str]
    ) -> float:
        """Calculate suppression ratio."""
        if not quasi_identifiers:
            return 0.0
        
        existing_qis = [qi for qi in quasi_identifiers if qi in anon_df.columns]
        if not existing_qis:
            return 0.0
        
        try:
            qi_df = anon_df[existing_qis]
            suppressed = (qi_df == '*').sum().sum()
            total = len(qi_df) * len(existing_qis)
            return suppressed / total if total > 0 else 0.0
        except Exception:
            return 0.0

    def validate_constraints_only(
        self,
        df: pd.DataFrame,
        original_df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        k: int = 5,
        l: int = 2,
        t: float = 0.2
    ) -> Dict[str, ValidationResult]:
        """
        Validate constraints without executing transformations.
        
        Useful for checking if already-anonymized data satisfies constraints.
        """
        return self._validate_constraints(
            df, original_df, quasi_identifiers, sensitive_attributes,
            k, l, t
        )


# Standalone function for quick validation
def validate_k_anonymity(df: pd.DataFrame, quasi_identifiers: List[str], k: int = 5) -> Tuple[bool, int]:
    """
    Quick k-anonymity validation.
    
    Returns: (is_valid, actual_k)
    """
    engine = AnonymizationExecutionEngine()
    result = engine._validate_k_anonymity(df, quasi_identifiers, k)
    return result.is_valid, result.actual_value
