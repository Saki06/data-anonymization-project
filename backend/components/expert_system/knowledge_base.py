"""
Expert System Knowledge Base - Main Orchestrator
Integrates rules engine, SDC method catalog, and recommendation engine
for professional anonymization recommendations
"""

from typing import Dict, List, Any, Optional
from .models import RecommendationSet, Recommendation
from .recommendation_engine import RecommendationEngine
from .execution_engine import AnonymizationExecutionEngine, ExecutionResult
from .sdc_methods import SDCMethodCatalog
from .rules_engine import RulesEngine
from .pipeline_generator import PipelineGenerator, AnonymizationPipeline
from .decision_and_validation_agent import DecisionAgent, PostValidationAgent, ValidationReport, ParetoSolution
import pandas as pd
import numpy as np
import json


class AnonymizationKnowledgeBase:
    """
    Professional expert system for SDC anonymization recommendations.
    
    Integrates:
    - RulesEngine: Evaluates profiling metrics against rules
    - SDCMethodCatalog: Comprehensive SDC method library
    - RecommendationEngine: Generates intelligent recommendations
    """

    def __init__(self):
        """Initialize the expert system with all components."""
        self.recommendation_engine = RecommendationEngine()
        self.sdc_catalog = self.recommendation_engine.sdc_catalog
        self.rules_engine = self.recommendation_engine.rules_engine
        # Initialize the Execution Engine for enforcing privacy constraints
        self.execution_engine = AnonymizationExecutionEngine(max_iterations=5)
        
        # Initialize new agents (Agent 5, 7, 9)
        self.pipeline_generator = PipelineGenerator()  # Agent 5
        self.decision_agent = DecisionAgent()  # Agent 7
        self.post_validation_agent = PostValidationAgent()  # Agent 9
        
        self._recommendation_history = []
        # expose agent manager for registrations
        self.agent_manager = self.recommendation_engine.agent_manager

    def recommend_methods(self, profile: Dict[str, Any]) -> RecommendationSet:
        """
        Generate recommendations based on profiling results.
        
        Args:
            profile: Dict containing metrics from RiskAnalyzer
            
        Returns:
            RecommendationSet with primary/secondary methods and assessment
        """
        recommendation_set = self.recommendation_engine.generate_recommendations(profile)
        
        # Store in history for learning/feedback
        self._recommendation_history.append({
            "profile": profile,
            "recommendation": recommendation_set
        })
        
        return recommendation_set

    def get_recommendations_dict(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get recommendations as dict (for API/serialization compatibility).
        
        Args:
            profile: Dict containing metrics from RiskAnalyzer
            
        Returns:
            Dict with recommendations and details
        """
        rec_set = self.recommend_methods(profile)
        triggered_rules = self.get_triggered_rules(profile)
        
        return {
            "primary_method": rec_set.primary_method,
            "secondary_methods": rec_set.secondary_methods,
            "hybrid_approach": rec_set.hybrid_approach,
            "overall_privacy_level": rec_set.overall_privacy_level,
            "overall_utility_impact": rec_set.overall_utility_impact,
            "triggered_rules": triggered_rules,
            "recommendations": [
                {
                    "method": r.method,
                    "details": r.details,
                    "privacy_level": r.privacy_level,
                    "utility_impact": r.utility_impact,
                    "explanation": r.explanation,
                    "confidence": r.confidence,
                    "ai_feedback": r.ai_feedback
                }
                for r in rec_set.recommendations
            ],
            "additional_notes": rec_set.additional_notes
        }

    def add_ai_feedback(self, method_key: str, feedback: str) -> None:
        """
        Store feedback from AI agents about method effectiveness.
        
        Args:
            method_key: SDC method key (e.g., 'k_anonymity')
            feedback: Feedback string from AI agent
        """
        self.recommendation_engine.add_ai_agent_feedback(method_key, feedback)

    def register_ai_agent(self, agent) -> None:
        """Register a new AI agent to the recommendation pipeline."""
        self.agent_manager.register_agent(agent)

    def get_all_methods(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all SDC methods with details.
        
        Returns:
            Dict mapping method_key to method details
        """
        result = {}
        for key, method in self.sdc_catalog.get_all_methods().items():
            result[key] = {
                "label": method.label,
                "description": method.description,
                "privacy_level": method.privacy_level,
                "utility_impact": method.utility_impact,
                "parameters": method.parameters,
                "applicable_to": method.applicable_to,
                "ai_feedback": method.ai_feedback
            }
        return result

    def get_method_details(self, method_key: str) -> Dict[str, Any]:
        """Get detailed information about a specific SDC method."""
        return self.recommendation_engine.get_method_details(method_key)

    def get_triggered_rules(self, profile: Dict[str, Any]) -> List[str]:
        """Get list of rules triggered by the profile."""
        return self.rules_engine.evaluate_profile(profile)

    def get_rule_details(self, rule_name: str) -> Dict[str, Any]:
        """Get details about a specific rule."""
        rule = self.rules_engine.get_rule_details(rule_name)
        if not rule:
            return {}
        return {
            "name": rule.name,
            "explanation": rule.explanation,
            "severity": rule.severity,
            "recommended_methods": rule.recommended_methods
        }

    def add_custom_rule(self, rule_name: str, conditions: List, recommended_methods: List[str], explanation: str, severity: str = "Medium") -> None:
        """Allow addition of custom rules (e.g., by users or AI agents)."""
        from .models import Rule
        custom_rule = Rule(
            name=rule_name,
            conditions=conditions,
            recommended_methods=recommended_methods,
            explanation=explanation,
            severity=severity
        )
        self.rules_engine.add_custom_rule(custom_rule)

    def add_custom_sdc_method(self, method_key: str, label: str, description: str, privacy_level: str, utility_impact: str, **kwargs) -> None:
        """Allow addition of custom SDC methods (e.g., organization-specific methods)."""
        from .models import SDCMethod
        method = SDCMethod(
            key=method_key,
            label=label,
            description=description,
            privacy_level=privacy_level,
            utility_impact=utility_impact,
            **kwargs
        )
        self.sdc_catalog.add_method(method)

    def export_recommendations(self, filepath: str, format: str = "json") -> None:
        """Export recommendation history for analysis."""
        if format == "json":
            with open(filepath, 'w') as f:
                json.dump(
                    [
                        {
                            "profile": h["profile"],
                            "recommendation": {
                                "primary": h["recommendation"].primary_method,
                                "secondary": h["recommendation"].secondary_methods,
                                "hybrid": h["recommendation"].hybrid_approach
                            }
                        }
                        for h in self._recommendation_history
                    ],
                    f,
                    indent=2,
                    default=str
                )
        elif format == "csv":
            df_data = []
            for h in self._recommendation_history:
                df_data.append({
                    "primary_method": h["recommendation"].primary_method,
                    "secondary_methods": ", ".join(h["recommendation"].secondary_methods),
                    "privacy_level": h["recommendation"].overall_privacy_level,
                    "utility_impact": h["recommendation"].overall_utility_impact
                })
            pd.DataFrame(df_data).to_csv(filepath, index=False)

    def get_recommendation_statistics(self) -> Dict[str, Any]:
        """Get statistics about recommendations made so far."""
        if not self._recommendation_history:
            return {}
        
        methods = []
        for h in self._recommendation_history:
            methods.append(h["recommendation"].primary_method)
        
        method_counts = pd.Series(methods).value_counts().to_dict()
        
        return {
            "total_recommendations": len(self._recommendation_history),
            "method_distribution": method_counts,
            "avg_privacy_level": self._avg_level([h["recommendation"].overall_privacy_level for h in self._recommendation_history]),
            "avg_utility_impact": self._avg_level([h["recommendation"].overall_utility_impact for h in self._recommendation_history])
        }

    @staticmethod
    def _avg_level(levels: List[str]) -> str:
        """Calculate average privacy/utility level."""
        if not levels:
            return "Medium"
        level_order = {"Low": 0, "Medium": 1, "High": 2, "Very High": 3}
        avg = sum(level_order.get(l, 1) for l in levels) / len(levels)
        reverse_order = {0: "Low", 1: "Medium", 2: "High", 3: "Very High"}
        return reverse_order.get(round(avg), "Medium")

    def execute_and_validate(
        self,
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        profile: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute recommended methods with full validation and constraint enforcement.
        
        This is the core method that converts recommendations into enforced privacy:
        1. Generate recommendations based on profile
        2. Execute transformations
        3. Validate constraints (k-anonymity, l-diversity, t-closeness)
        4. Iterate if violations occur
        
        Args:
            df: Original dataframe
            quasi_identifiers: List of QI column names
            sensitive_attributes: List of sensitive attribute names
            profile: Optional profile metrics (will generate if not provided)
            parameters: Optional execution parameters (k, l, t, generalization_level)
            
        Returns:
            Dict with execution results and validation status
        """
        # Generate recommendations if not provided
        if profile is None:
            profile = {}
        
        recommendations = self.recommend_methods(profile)
        
        # Execute with validation
        execution_result = self.execution_engine.execute_with_validation(
            df=df,
            quasi_identifiers=quasi_identifiers,
            sensitive_attributes=sensitive_attributes,
            recommendations=recommendations,
            initial_params=parameters
        )
        
        # Convert ExecutionResult to dict for API response
        result_dict = {
            "success": execution_result.success,
            "applied_methods": execution_result.applied_methods,
            "parameters_used": execution_result.parameters_used,
            "validation_results": execution_result.validation_results,
            "violations": execution_result.violations,
            "iterations_performed": execution_result.iterations_performed,
            "final_k_value": execution_result.final_k_value,
            "final_l_value": execution_result.final_l_value,
            "final_t_value": execution_result.final_t_value,
            "suppression_ratio": execution_result.suppression_ratio
        }
        
        # Add anonymized data sample if successful
        if execution_result.anonymized_data is not None:
            sample_data = execution_result.anonymized_data.head(20).to_dict('records')
            # Clean up NaN values
            for record in sample_data:
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None
                    elif isinstance(value, (np.integer, np.floating)):
                        record[key] = float(value)
            result_dict["sample_data"] = sample_data
        
        # Add recommendations that were used
        result_dict["recommendations_used"] = {
            "primary_method": recommendations.primary_method,
            "secondary_methods": recommendations.secondary_methods,
            "hybrid_approach": recommendations.hybrid_approach,
            "overall_privacy_level": recommendations.overall_privacy_level,
            "overall_utility_impact": recommendations.overall_utility_impact
        }
        
        return result_dict
    
    # ========== NEW METHODS FOR AGENTS 5, 7, 9 ==========
    
    def generate_anonymization_pipelines(
        self,
        recommendations: Dict[str, Any],
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        dataset_size: int = 1000,
        num_pipelines: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Agent 5: Generate multiple anonymization pipelines.
        
        Args:
            recommendations: Recommendation set from knowledge base
            quasi_identifiers: List of QI column names
            sensitive_attributes: List of sensitive attribute names
            dataset_size: Number of records in dataset
            num_pipelines: Number of pipelines to generate
            
        Returns:
            List of pipeline dictionaries
        """
        pipelines = self.pipeline_generator.generate_pipelines(
            recommendations=recommendations,
            quasi_identifiers=quasi_identifiers,
            sensitive_attributes=sensitive_attributes,
            dataset_size=dataset_size,
            num_pipelines=num_pipelines
        )
        
        return self.pipeline_generator.export_pipelines_to_dict()
    
    def select_best_solution_from_pareto(
        self,
        pipelines: List[Dict[str, Any]],
        privacy_scores: List[float],
        utility_scores: List[float],
        mode: str = "auto",
        weight_privacy: float = 0.6,
        weight_utility: float = 0.4
    ) -> Dict[str, Any]:
        """
        Agent 7: Select best solution from Pareto front.
        
        Args:
            pipelines: List of pipeline dictionaries
            privacy_scores: Privacy score for each pipeline
            utility_scores: Utility score for each pipeline
            mode: 'auto' or 'human'
            weight_privacy: Weight for privacy metric
            weight_utility: Weight for utility metric
            
        Returns:
            Selected solution details and rationale
        """
        # Evaluate Pareto front
        solutions = self.decision_agent.evaluate_pareto_front(
            pipelines=pipelines,
            privacy_scores=privacy_scores,
            utility_scores=utility_scores
        )
        
        if mode == "auto":
            selected = self.decision_agent.auto_select_best_solution(
                weight_privacy=weight_privacy,
                weight_utility=weight_utility
            )
        else:
            # Return top solutions for human selection
            return {
                "mode": "human",
                "pareto_front": self.decision_agent.get_pareto_front_for_user(top_k=5)
            }
        
        rationale = self.decision_agent.get_selection_rationale(selected)
        
        return {
            "mode": "auto",
            "selected_solution": selected.to_dict(),
            "selection_rationale": rationale
        }
    
    def select_solution_by_user_preference(
        self,
        pipeline_id: int,
        user_preference: str = "balanced"
    ) -> Dict[str, Any]:
        """
        User manually selects solution from Pareto front.
        
        Args:
            pipeline_id: ID of selected pipeline
            user_preference: 'privacy', 'utility', or 'balanced'
            
        Returns:
            Selected solution details
        """
        selected = self.decision_agent.select_by_user_preference(
            pipeline_id=pipeline_id,
            user_preference=user_preference
        )
        
        return {
            "selected_solution": selected.to_dict(),
            "user_preference": user_preference
        }
    
    def post_validate_anonymization(
        self,
        anonymized_df: pd.DataFrame,
        original_df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        required_k: int = 5,
        required_l: int = 2,
        required_t: float = 0.2
    ) -> Dict[str, Any]:
        """
        Agent 9: Post-validate anonymized data.
        
        Args:
            anonymized_df: Anonymized dataset
            original_df: Original dataset
            quasi_identifiers: List of QI columns
            sensitive_attributes: List of sensitive attribute columns
            required_k: Required k-anonymity level
            required_l: Required l-diversity level
            required_t: Required t-closeness threshold
            
        Returns:
            Validation report with violations and remediation actions
        """
        validation_report = self.post_validation_agent.validate_anonymized_data(
            anonymized_df=anonymized_df,
            original_df=original_df,
            quasi_identifiers=quasi_identifiers,
            sensitive_attributes=sensitive_attributes,
            required_k=required_k,
            required_l=required_l,
            required_t=required_t
        )
        
        return validation_report.to_dict()
    
    def get_re_optimization_parameters(
        self,
        validation_report: ValidationReport
    ) -> Dict[str, Any]:
        """
        Generate parameters for re-optimization if constraints not met.
        
        Args:
            validation_report: ValidationReport from post-validation
            
        Returns:
            Suggested parameters for re-optimization
        """
        if validation_report.is_valid:
            return {"re_optimization_needed": False}
        
        new_params = {
            "re_optimization_needed": True,
            "recommended_adjustments": []
        }
        
        # Suggest parameter adjustments based on violations
        if not validation_report.k_anonymity_met:
            new_k = min(validation_report.required_k + 2, 20)
            new_params["recommended_adjustments"].append(f"Increase k from {validation_report.actual_k} to {new_k}")
            new_params["suggested_k"] = new_k
        
        if not validation_report.l_diversity_met:
            new_l = min(validation_report.required_l + 1, 10)
            new_params["recommended_adjustments"].append(f"Increase l from {validation_report.actual_l} to {new_l}")
            new_params["suggested_l"] = new_l
        
        if not validation_report.t_closeness_met:
            new_t = max(validation_report.required_t * 0.8, 0.1)
            new_params["recommended_adjustments"].append(f"Lower t from {validation_report.actual_t:.4f} to {new_t:.4f}")
            new_params["suggested_t"] = new_t
        
        new_params["remediation_actions"] = validation_report.remediation_actions
        
        return new_params
