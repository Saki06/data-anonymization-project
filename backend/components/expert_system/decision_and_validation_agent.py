"""
Decision Agent (Agent 7) - Pareto Front Selection
Post-Validation Agent (Agent 9) - Constraint Re-validation

Agent 7: Decision Agent
- Input: Pareto-optimal set of anonymization solutions
- Modes:
  * Auto-select best trade-off (using distance to ideal point)
  * Human-in-loop selection (return Pareto front for user selection)
- Output: selected_pipeline + selection_rationale

Agent 9: Post-Validation Agent
- Input: Anonymized dataset + selected pipeline
- Tasks:
  * Recompute k-anonymity, l-diversity, t-closeness
  * Check if constraints are met
  * If violated, trigger re-optimization or adjustment
- Output: validation_report + remediation_actions
"""

from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class ParetoSolution:
    """Single solution on Pareto front."""
    pipeline_id: int
    pipeline: Dict[str, Any]
    privacy_score: float  # Lower is better (minimize disclosure risk)
    utility_score: float  # Lower is better (minimize information loss)
    k_value: Optional[int] = None
    l_value: Optional[int] = None
    t_value: Optional[float] = None
    
    def distance_to_ideal(self) -> float:
        """Calculate distance to ideal point (0, 0)."""
        return np.sqrt(self.privacy_score**2 + self.utility_score**2)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "pipeline_id": self.pipeline_id,
            "pipeline": self.pipeline,
            "privacy_score": round(self.privacy_score, 4),
            "utility_score": round(self.utility_score, 4),
            "k_value": self.k_value,
            "l_value": self.l_value,
            "t_value": self.t_value,
            "distance_to_ideal": round(self.distance_to_ideal(), 4)
        }


@dataclass
class ValidationReport:
    """Post-anonymization validation report."""
    is_valid: bool
    k_anonymity_met: bool
    l_diversity_met: bool
    t_closeness_met: bool
    actual_k: int
    actual_l: int
    actual_t: float
    required_k: int
    required_l: int
    required_t: float
    violations: List[Dict[str, Any]] = field(default_factory=list)
    remediation_actions: List[str] = field(default_factory=list)
    re_optimization_needed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_valid": self.is_valid,
            "k_anonymity_met": self.k_anonymity_met,
            "l_diversity_met": self.l_diversity_met,
            "t_closeness_met": self.t_closeness_met,
            "actual_k": self.actual_k,
            "actual_l": self.actual_l,
            "actual_t": round(self.actual_t, 4),
            "required_k": self.required_k,
            "required_l": self.required_l,
            "required_t": round(self.required_t, 4),
            "violations": self.violations,
            "remediation_actions": self.remediation_actions,
            "re_optimization_needed": self.re_optimization_needed
        }


class DecisionAgent:
    """
    Pareto Front Selection Agent
    
    Selects the best anonymization solution from Pareto-optimal set.
    Supports both automatic selection and human-in-the-loop modes.
    """
    
    def __init__(self):
        """Initialize decision agent."""
        self.pareto_front: List[ParetoSolution] = []
        self.selection_mode: str = "auto"  # 'auto' or 'human'
        self.last_selection: Optional[ParetoSolution] = None
    
    def evaluate_pareto_front(
        self,
        pipelines: List[Dict[str, Any]],
        privacy_scores: List[float],
        utility_scores: List[float],
        k_values: Optional[List[int]] = None,
        l_values: Optional[List[int]] = None,
        t_values: Optional[List[float]] = None
    ) -> List[ParetoSolution]:
        """
        Evaluate and rank pipelines on Pareto front.
        
        Args:
            pipelines: List of pipeline dictionaries
            privacy_scores: Privacy scores for each pipeline
            utility_scores: Utility scores for each pipeline
            k_values: Optional k-anonymity values
            l_values: Optional l-diversity values
            t_values: Optional t-closeness values
            
        Returns:
            List of ParetoSolution objects sorted by quality
        """
        self.pareto_front = []
        
        for i, (pipeline, privacy, utility) in enumerate(zip(pipelines, privacy_scores, utility_scores)):
            solution = ParetoSolution(
                pipeline_id=i,
                pipeline=pipeline,
                privacy_score=privacy,
                utility_score=utility,
                k_value=k_values[i] if k_values else None,
                l_value=l_values[i] if l_values else None,
                t_value=t_values[i] if t_values else None
            )
            self.pareto_front.append(solution)
        
        # Sort by distance to ideal point
        self.pareto_front.sort(key=lambda x: x.distance_to_ideal())
        
        return self.pareto_front
    
    def auto_select_best_solution(
        self,
        weight_privacy: float = 0.6,
        weight_utility: float = 0.4
    ) -> ParetoSolution:
        """
        Automatically select best solution using weighted score.
        
        Args:
            weight_privacy: Weight for privacy (0-1)
            weight_utility: Weight for utility (0-1)
            
        Returns:
            Best ParetoSolution based on weighted score
        """
        if not self.pareto_front:
            raise ValueError("Pareto front is empty")
        
        # Normalize scores
        privacy_scores = np.array([s.privacy_score for s in self.pareto_front])
        utility_scores = np.array([s.utility_score for s in self.pareto_front])
        
        privacy_norm = privacy_scores / (privacy_scores.max() + 1e-10)
        utility_norm = utility_scores / (utility_scores.max() + 1e-10)
        
        # Calculate weighted score
        weighted_scores = weight_privacy * privacy_norm + weight_utility * utility_norm
        best_idx = np.argmin(weighted_scores)
        
        self.last_selection = self.pareto_front[best_idx]
        logger.info(f"Auto-selected solution {best_idx}: {self.last_selection}")
        
        return self.last_selection
    
    def get_pareto_front_for_user(self, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Get top solutions for human-in-the-loop selection.
        
        Args:
            top_k: Number of top solutions to return
            
        Returns:
            List of top solutions as dictionaries
        """
        if not self.pareto_front:
            raise ValueError("Pareto front is empty")
        
        # Return top_k solutions
        top_solutions = self.pareto_front[:top_k]
        return [s.to_dict() for s in top_solutions]
    
    def select_by_user_preference(
        self,
        pipeline_id: int,
        user_preference: str = "balanced"
    ) -> ParetoSolution:
        """
        Select solution based on user preference.
        
        Args:
            pipeline_id: ID of selected pipeline
            user_preference: 'privacy' (minimize risk), 'utility' (maximize info), 'balanced'
            
        Returns:
            Selected ParetoSolution
        """
        # Find solution by ID
        selected = None
        for solution in self.pareto_front:
            if solution.pipeline_id == pipeline_id:
                selected = solution
                break
        
        if not selected:
            raise ValueError(f"Pipeline {pipeline_id} not found in Pareto front")
        
        self.last_selection = selected
        logger.info(f"User selected solution {pipeline_id} (preference: {user_preference})")
        
        return selected
    
    def get_selection_rationale(self, solution: Optional[ParetoSolution] = None) -> Dict[str, Any]:
        """Get rationale for the selected solution."""
        sel = solution or self.last_selection
        
        if not sel:
            return {"rationale": "No solution selected"}
        
        return {
            "selected_pipeline_id": sel.pipeline_id,
            "privacy_score": round(sel.privacy_score, 4),
            "utility_score": round(sel.utility_score, 4),
            "distance_to_ideal": round(sel.distance_to_ideal(), 4),
            "k_value": sel.k_value,
            "l_value": sel.l_value,
            "t_value": sel.t_value,
            "rationale": f"Best trade-off with privacy_score={sel.privacy_score:.4f} and utility_score={sel.utility_score:.4f}",
            "total_pareto_solutions": len(self.pareto_front)
        }


class PostValidationAgent:
    """
    Post-Validation Agent
    
    Re-validates anonymized data after transformation.
    Checks if k-anonymity, l-diversity, and t-closeness constraints are met.
    Recommends remediation actions if violations occur.
    """
    
    def __init__(self):
        """Initialize post-validation agent."""
        self.last_validation: Optional[ValidationReport] = None
    
    def validate_anonymized_data(
        self,
        anonymized_df: pd.DataFrame,
        original_df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        required_k: int = 5,
        required_l: int = 2,
        required_t: float = 0.2
    ) -> ValidationReport:
        """
        Validate anonymized data against privacy constraints.
        
        Args:
            anonymized_df: Anonymized dataset
            original_df: Original dataset (for t-closeness calculation)
            quasi_identifiers: List of QI columns
            sensitive_attributes: List of sensitive attribute columns
            required_k: Required k-anonymity level
            required_l: Required l-diversity level
            required_t: Required t-closeness threshold
            
        Returns:
            ValidationReport with detailed results
        """
        # Check k-anonymity
        actual_k, k_met = self._check_k_anonymity(anonymized_df, quasi_identifiers, required_k)
        
        # Check l-diversity
        actual_l, l_met = self._check_l_diversity(
            anonymized_df, quasi_identifiers, sensitive_attributes, required_l
        )
        
        # Check t-closeness
        actual_t, t_met = self._check_t_closeness(
            anonymized_df, original_df, quasi_identifiers, sensitive_attributes, required_t
        )
        
        # Determine overall validity
        is_valid = k_met and l_met and t_met
        
        # Identify violations
        violations = []
        if not k_met:
            violations.append({
                "constraint": "k-anonymity",
                "required": required_k,
                "actual": actual_k,
                "message": f"k-anonymity {actual_k} < {required_k}"
            })
        if not l_met:
            violations.append({
                "constraint": "l-diversity",
                "required": required_l,
                "actual": actual_l,
                "message": f"l-diversity {actual_l} < {required_l}"
            })
        if not t_met:
            violations.append({
                "constraint": "t-closeness",
                "required": required_t,
                "actual": actual_t,
                "message": f"t-closeness {actual_t:.4f} > {required_t}"
            })
        
        # Generate remediation actions
        remediation = self._generate_remediation_actions(violations)
        re_opt_needed = len(violations) > 0
        
        self.last_validation = ValidationReport(
            is_valid=is_valid,
            k_anonymity_met=k_met,
            l_diversity_met=l_met,
            t_closeness_met=t_met,
            actual_k=actual_k,
            actual_l=actual_l,
            actual_t=actual_t,
            required_k=required_k,
            required_l=required_l,
            required_t=required_t,
            violations=violations,
            remediation_actions=remediation,
            re_optimization_needed=re_opt_needed
        )
        
        return self.last_validation
    
    def _check_k_anonymity(
        self,
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        required_k: int
    ) -> Tuple[int, bool]:
        """Check k-anonymity constraint."""
        if not quasi_identifiers or not all(qi in df.columns for qi in quasi_identifiers):
            return 0, False
        
        try:
            qi_df = df[quasi_identifiers]
            groups = qi_df.groupby(list(quasi_identifiers)).size()
            min_k = int(groups.min()) if len(groups) > 0 else 0
            return min_k, min_k >= required_k
        except Exception as e:
            logger.error(f"Error checking k-anonymity: {e}")
            return 0, False
    
    def _check_l_diversity(
        self,
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        required_l: int
    ) -> Tuple[int, bool]:
        """Check l-diversity constraint."""
        if not quasi_identifiers or not sensitive_attributes:
            return 0, True
        
        try:
            min_l = float('inf')
            
            for sens_attr in sensitive_attributes:
                if sens_attr not in df.columns:
                    continue
                
                # Group by quasi-identifiers
                existing_qis = [qi for qi in quasi_identifiers if qi in df.columns]
                if not existing_qis:
                    continue
                
                groups = df.groupby(list(existing_qis))
                
                for group_key, group_data in groups:
                    distinct_values = group_data[sens_attr].nunique()
                    min_l = min(min_l, distinct_values)
            
            if min_l == float('inf'):
                min_l = 0
            
            return int(min_l), min_l >= required_l
        except Exception as e:
            logger.error(f"Error checking l-diversity: {e}")
            return 0, False
    
    def _check_t_closeness(
        self,
        anon_df: pd.DataFrame,
        original_df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        required_t: float
    ) -> Tuple[float, bool]:
        """Check t-closeness constraint."""
        if not quasi_identifiers or not sensitive_attributes:
            return 0.0, True
        
        try:
            max_distance = 0.0
            
            for sens_attr in sensitive_attributes:
                if sens_attr not in anon_df.columns or sens_attr not in original_df.columns:
                    continue
                
                # Get global distribution
                global_dist = original_df[sens_attr].value_counts(normalize=True).to_dict()
                
                # Check max TVD across groups
                existing_qis = [qi for qi in quasi_identifiers if qi in anon_df.columns]
                if not existing_qis:
                    continue
                
                groups = anon_df.groupby(list(existing_qis))
                
                for group_key, group_data in groups:
                    local_dist = group_data[sens_attr].value_counts(normalize=True).to_dict()
                    
                    # Calculate TVD (Total Variation Distance)
                    tvd = 0.5 * sum(abs(local_dist.get(k, 0) - global_dist.get(k, 0)) 
                                    for k in set(local_dist.keys()) | set(global_dist.keys()))
                    
                    max_distance = max(max_distance, tvd)
            
            return max_distance, max_distance <= required_t
        except Exception as e:
            logger.error(f"Error checking t-closeness: {e}")
            return 1.0, False
    
    def _generate_remediation_actions(self, violations: List[Dict[str, Any]]) -> List[str]:
        """Generate suggested remediation actions for violations."""
        actions = []
        
        for violation in violations:
            constraint = violation.get('constraint', '')
            
            if constraint == 'k-anonymity':
                actions.append("Increase generalization level for quasi-identifiers")
                actions.append("Apply stronger suppression of rare combinations")
                actions.append("Increase k-anonymity parameter")
                
            elif constraint == 'l-diversity':
                actions.append("Apply l-diversity transformation with higher l value")
                actions.append("Generalize quasi-identifiers further")
                actions.append("Suppress rare sensitive attribute values")
                
            elif constraint == 't-closeness':
                actions.append("Apply t-closeness transformation with lower threshold")
                actions.append("Generalize quasi-identifiers more aggressively")
                actions.append("Apply perturbation to sensitive attributes")
        
        # Add re-optimization suggestion if multiple violations
        if len(violations) > 1:
            actions.append("RECOMMENDED: Run re-optimization with stricter parameters")
        
        return list(set(actions))  # Remove duplicates
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """Get summary of last validation."""
        if not self.last_validation:
            return {"status": "No validation performed yet"}
        
        return self.last_validation.to_dict()
