"""
Recommendation engine - generates recommendations based on rules and profile analysis
"""

from typing import Dict, List, Any, Optional
from collections import Counter
from .models import Recommendation, RecommendationSet
from .sdc_methods import SDCMethodCatalog
from .rules_engine import RulesEngine
from .ai_agents import AgentManager


class RecommendationEngine:
    """Generates smart, adaptive recommendations for SDC method selection."""

    def __init__(self):
        self.sdc_catalog = SDCMethodCatalog()
        self.rules_engine = RulesEngine()
        self.agent_manager = AgentManager()  # manages AI agents

    def generate_recommendations(self, profile: Dict[str, Any]) -> RecommendationSet:
        """
        Main entry point: Generate full recommendation set for a profile.
        
        Args:
            profile: Dict containing profiling metrics from risk analyzer
            
        Returns:
            RecommendationSet with primary/secondary methods and overall assessment
        """
        # Evaluate rules against profile
        rule_recommendations = self.rules_engine.get_recommendations_for_profile(profile)
        
        if not rule_recommendations:
            return self._get_default_recommendation()

        # Collect all recommended methods with frequency
        method_counter = Counter()
        rule_to_methods = {}
        
        for rule_name, methods in rule_recommendations.items():
            rule_to_methods[rule_name] = methods
            for method in methods:
                method_counter[method] += 1

        # Generate individual recommendations with confidence scores
        recommendations = []
        method_scores = {}  # Track combined frequency + confidence score
        
        for method_key, frequency in method_counter.most_common():
            rec = self._create_recommendation(method_key, rule_to_methods, profile)
            if rec:
                recommendations.append(rec)
                confidence = rec.confidence
                # Use higher weight for confidence to favor high-confidence methods
                combined_score = frequency + (confidence * 10)
                method_scores[method_key] = combined_score
        
        # Determine primary method using confidence-based priority
        primary_method = self._determine_primary_method(
            recommendations, method_scores, method_counter, profile
        )
        
        secondary_methods = [rec.method for rec in recommendations[1:3]] if len(recommendations) > 1 else []
        
        # Check if hybrid approach is recommended
        hybrid_approach = any(rec.method == "hybrid" for rec in recommendations)
        
        # Calculate overall privacy/utility levels
        overall_privacy = self._aggregate_level([rec.privacy_level for rec in recommendations])
        overall_utility = self._aggregate_level([rec.utility_impact for rec in recommendations])

        # prepare RecommendationSet
        rec_set = RecommendationSet(
            recommendations=recommendations,
            primary_method=primary_method,
            secondary_methods=secondary_methods,
            hybrid_approach=hybrid_approach,
            overall_privacy_level=overall_privacy,
            overall_utility_impact=overall_utility,
            additional_notes=self._generate_additional_notes(profile, recommendations)
        )

        # let agents review and possibly modify the recommendations
        if self.agent_manager and self.agent_manager.agents:
            self.agent_manager.evaluate(profile, rec_set)

        return rec_set

    def _determine_primary_method(
        self, 
        recommendations: List[Recommendation], 
        method_scores: Dict[str, float],
        method_counter: Counter,
        profile: Dict[str, Any]
    ) -> str:
        """Determine the primary method based on scores and confidence."""
        
        # Find methods with very high confidence (>= 0.95)
        high_conf_recs = [r for r in recommendations if r.confidence >= 0.95]
        
        if high_conf_recs:
            # Sort by score
            sorted_scores = sorted(method_scores.items(), key=lambda x: x[1], reverse=True)
            highest_key = sorted_scores[0][0]
            
            # Check if highest scoring method has high confidence
            for rec in high_conf_recs:
                rec_key = rec.method.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')
                if highest_key.replace('_', '') in rec_key or rec_key in highest_key.replace('_', ''):
                    return rec.method
            
            # Special handling for PRAM when categorical QIs present
            if 'has_categorical_qi' in profile and profile.get('has_categorical_qi', False):
                for rec in high_conf_recs:
                    if 'pram' in rec.method.lower():
                        return rec.method
            
            # Use first high confidence method
            return high_conf_recs[0].method
        
        # Fallback to highest scoring method
        sorted_methods = sorted(method_scores.items(), key=lambda x: x[1], reverse=True)
        highest_key = sorted_methods[0][0]
        for rec in recommendations:
            rec_key = rec.method.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')
            if highest_key.replace('_', '') in rec_key:
                return rec.method
        
        return "k_anonymity"

    def _create_recommendation(self, method_key: str, rule_mapping: Dict, profile: Dict) -> Optional[Recommendation]:
        """Create a single recommendation for a method."""
        method = self.sdc_catalog.get_method(method_key)
        if not method:
            return None

        # Find which rules triggered this method
        triggered_for = [rule for rule, methods in rule_mapping.items() if method_key in methods]
        reason = "; ".join(triggered_for[:2])  # Limit to 2 reasons for brevity

        return Recommendation(
            method=method.label,
            details=method.description,
            privacy_level=method.privacy_level,
            utility_impact=method.utility_impact,
            explanation=f"Recommended due to: {reason}",
            ai_feedback=method.ai_feedback,
            confidence=self._calculate_confidence(method_key, profile),
            reason=reason
        )

    def _calculate_confidence(self, method_key: str, profile: Dict) -> float:
        """
        Calculate confidence score (0-1) for a recommended method based on profile alignment.
        """
        confidence = 0.8  # baseline
        
        # Adjust based on profile characteristics
        if method_key == "k_anonymity" and profile.get('min_group_size', 100) < 3:
            confidence = 0.95
        elif method_key == "differential_privacy" and profile.get('dp_required', False):
            confidence = 1.0
        elif method_key == "synthetic_data" and profile.get('synthetic_suitable', False):
            confidence = 0.9
        elif method_key == "psu_aggregation" and profile.get('has_psu', False):
            confidence = 0.95
        # Higher confidence for PRAM when categorical QIs are present
        elif method_key == "pram":
            if profile.get('has_categorical_qi', False) and profile.get('categorical_risk_score', 0) > 0.3:
                confidence = 1.0  # Very high confidence for PRAM with categorical QIs
            elif profile.get('categorical_risk_score', 0) > 0.5:
                confidence = 0.95
        
        return min(confidence, 1.0)

    def _aggregate_level(self, levels: List[str]) -> str:
        """
        Aggregate multiple privacy/utility levels into a single level.
        Priority: Very High > High > Medium > Low
        """
        if not levels:
            return "Medium"
        
        level_order = {"Low": 0, "Medium": 1, "High": 2, "Very High": 3}
        max_level = max((level_order.get(l, 1) for l in levels), default=1)
        
        reverse_order = {0: "Low", 1: "Medium", 2: "High", 3: "Very High"}
        return reverse_order.get(max_level, "Medium")

    def _get_default_recommendation(self) -> RecommendationSet:
        """Return default recommendation when no rules are triggered."""
        method = self.sdc_catalog.get_method("k_anonymity")
        rec = Recommendation(
            method=method.label,
            details=method.description,
            privacy_level=method.privacy_level,
            utility_impact=method.utility_impact,
            explanation="No specific high-risk patterns detected; k-anonymity baseline recommended.",
            confidence=0.7
        )
        return RecommendationSet(
            recommendations=[rec],
            primary_method="K-Anonymity",
            secondary_methods=[],
            hybrid_approach=False,
            overall_privacy_level="Medium",
            overall_utility_impact="Medium",
            additional_notes="Dataset appears low-risk; basic anonymization sufficient."
        )

    def _generate_additional_notes(self, profile: Dict, recommendations: List[Recommendation]) -> str:
        """Generate additional contextual notes about the recommendations."""
        notes = []

        if profile.get('has_psu', False):
            notes.append("PSU detected: ensure aggregation/generalization is applied before release.")
        
        if profile.get('num_high_risk', 0) >= 3:
            notes.append("Multiple risk categories present: hybrid approach with layered protection advised.")
        
        if profile.get('unique_ratio', 0) > 0.9:
            notes.append("High cardinality in QIs: consider aggressive generalization.")
        
        if profile.get('sensitive_distinct', 100) < 3:
            notes.append("Low diversity in sensitive attribute: l-diversity or t-closeness critical.")
        
        if len(recommendations) > 3:
            notes.append("Multiple complementary methods recommended; apply in sequence for best protection.")

        return " ".join(notes) if notes else "Dataset characteristics support the primary method recommendation."

    def add_ai_agent_feedback(self, method_key: str, feedback: str):
        """Allow AI agents to provide feedback about method performance."""
        self.sdc_catalog.update_method_feedback(method_key, feedback)

    def register_agent(self, agent):
        """Register an AI agent with the recommendation engine."""
        self.agent_manager.register_agent(agent)

    def get_method_details(self, method_key: str) -> Dict[str, Any]:
        """Get detailed information about a specific SDC method."""
        method = self.sdc_catalog.get_method(method_key)
        if not method:
            return {}
        
        return {
            "key": method.key,
            "label": method.label,
            "description": method.description,
            "privacy_level": method.privacy_level,
            "utility_impact": method.utility_impact,
            "parameters": method.parameters,
            "applicable_to": method.applicable_to,
            "ai_feedback": method.ai_feedback
        }

