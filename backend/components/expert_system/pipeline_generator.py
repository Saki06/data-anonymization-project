"""
Pipeline Generator Agent (Agent 5)

Generates multiple anonymization pipeline combinations from recommended methods.
Each pipeline is a sequence of transformations with specific parameters.

Example:
    Pipeline A = [generalization(age,10), suppression(groups<5)]
    Pipeline B = [microaggregation(income,5), recoding(occupation)]
    Pipeline C = [k_anonymity(k=5), l_diversity(l=2), t_closeness(t=0.2)]
"""

from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np
from itertools import combinations, product


@dataclass
class AnonymizationStep:
    """Single transformation step in a pipeline."""
    method: str  # e.g., 'generalization', 'k_anonymity', 'microaggregation'
    target_columns: List[str]  # Columns to apply this method to
    parameters: Dict[str, Any]  # Method-specific parameters
    
    def __repr__(self):
        params_str = ", ".join(f"{k}={v}" for k, v in self.parameters.items())
        cols_str = ", ".join(self.target_columns)
        return f"{self.method}([{cols_str}], {params_str})"


@dataclass
class AnonymizationPipeline:
    """Complete anonymization pipeline - sequence of transformation steps."""
    steps: List[AnonymizationStep]
    privacy_target: Dict[str, Any]  # Target k, l, t values
    expected_privacy_level: str  # 'Low', 'Medium', 'High', 'Very High'
    expected_utility_impact: str  # Expected information loss
    name: str = ""
    
    def __repr__(self):
        step_names = " → ".join(str(s) for s in self.steps)
        return f"Pipeline({step_names})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize pipeline to dictionary."""
        return {
            "name": self.name,
            "steps": [
                {
                    "method": s.method,
                    "target_columns": s.target_columns,
                    "parameters": s.parameters
                }
                for s in self.steps
            ],
            "privacy_target": self.privacy_target,
            "expected_privacy_level": self.expected_privacy_level,
            "expected_utility_impact": self.expected_utility_impact
        }


class PipelineGenerator:
    """
    Generates multiple anonymization pipelines for exploration and optimization.
    
    Takes recommended methods and creates a population of diverse pipelines
    by varying:
    - Method selection (which methods to use)
    - Parameter ranges (k, l, t, generalization level)
    - Method ordering (sequence of transformations)
    """
    
    def __init__(self):
        """Initialize the pipeline generator."""
        self.generated_pipelines: List[AnonymizationPipeline] = []
    
    def generate_pipelines(
        self,
        recommendations: Dict[str, Any],
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        dataset_size: int = 1000,
        num_pipelines: int = 20
    ) -> List[AnonymizationPipeline]:
        """
        Generate multiple anonymization pipelines.
        
        Args:
            recommendations: Recommendation set with primary/secondary methods
            quasi_identifiers: List of QI column names
            sensitive_attributes: List of sensitive attribute names
            dataset_size: Number of records in dataset (for parameter tuning)
            num_pipelines: Approximate number of pipelines to generate
            
        Returns:
            List of AnonymizationPipeline objects
        """
        self.generated_pipelines = []
        
        # Extract methods from recommendations
        primary_method = recommendations.get('primary_method', 'k_anonymity')
        secondary_methods = recommendations.get('secondary_methods', [])
        triggered_rules = recommendations.get('triggered_rules', [])
        
        # Generate parameter variations
        param_variations = self._generate_parameter_variations(dataset_size, num_pipelines)
        
        # Generate single-method pipelines
        for method in [primary_method] + secondary_methods:
            for params in param_variations[:num_pipelines // 4]:
                pipeline = self._create_single_method_pipeline(
                    method, quasi_identifiers, sensitive_attributes, params
                )
                if pipeline:
                    self.generated_pipelines.append(pipeline)
        
        # Generate hybrid pipelines (combinations of methods)
        hybrid_combos = list(combinations([primary_method] + secondary_methods, 2))
        for combo in hybrid_combos[:num_pipelines // 3]:
            for params in param_variations[:2]:
                pipeline = self._create_hybrid_pipeline(
                    combo, quasi_identifiers, sensitive_attributes, params
                )
                if pipeline:
                    self.generated_pipelines.append(pipeline)
        
        # Generate rule-based pipelines from triggered rules
        for rule_name in triggered_rules[:5]:
            for params in param_variations[:2]:
                pipeline = self._create_rule_based_pipeline(
                    rule_name, quasi_identifiers, sensitive_attributes, params
                )
                if pipeline:
                    self.generated_pipelines.append(pipeline)
        
        # Limit to requested number and ensure diversity
        self.generated_pipelines = self._ensure_diversity(
            self.generated_pipelines[:num_pipelines],
            num_pipelines
        )
        
        return self.generated_pipelines
    
    def _generate_parameter_variations(self, dataset_size: int, num_variations: int) -> List[Dict[str, Any]]:
        """Generate parameter variations for testing."""
        # Calculate reasonable k values based on dataset size
        max_k = min(20, dataset_size // 10)
        k_values = list(set([2, 3, 5, 10] + [max_k // 2, max_k]))
        k_values = sorted([k for k in k_values if 2 <= k <= max_k])
        
        # l-diversity values
        l_values = [2, 3, 5]
        
        # t-closeness values
        t_values = [0.1, 0.2, 0.3]
        
        # Generalization levels
        gen_levels = [0.3, 0.5, 0.7]
        
        # Create combinations
        variations = []
        for k, l, t, gen_level in product(k_values[:3], l_values[:2], t_values, gen_levels):
            variations.append({
                "k": k,
                "l": l,
                "t": t,
                "generalization_level": gen_level,
                "perturbation_rate": 0.05,
                "seed": 42
            })
        
        # Return limited set for efficiency
        return variations[:num_variations]
    
    def _create_single_method_pipeline(
        self,
        method: str,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        parameters: Dict[str, Any]
    ) -> AnonymizationPipeline:
        """Create a single-method pipeline."""
        method_key = method.lower().replace('-', '_').replace(' ', '_')
        
        if 'k_anonymity' in method_key:
            steps = [
                AnonymizationStep(
                    method='k_anonymity',
                    target_columns=quasi_identifiers,
                    parameters={'k': parameters.get('k', 5)}
                )
            ]
            privacy_target = {'k': parameters.get('k', 5)}
            
        elif 'l_diversity' in method_key:
            steps = [
                AnonymizationStep(
                    method='generalization',
                    target_columns=quasi_identifiers,
                    parameters={'generalization_level': parameters.get('generalization_level', 0.5)}
                ),
                AnonymizationStep(
                    method='l_diversity',
                    target_columns=sensitive_attributes,
                    parameters={
                        'k': parameters.get('k', 5),
                        'l': parameters.get('l', 2)
                    }
                )
            ]
            privacy_target = {'k': parameters.get('k', 5), 'l': parameters.get('l', 2)}
            
        elif 't_closeness' in method_key:
            steps = [
                AnonymizationStep(
                    method='generalization',
                    target_columns=quasi_identifiers,
                    parameters={'generalization_level': parameters.get('generalization_level', 0.5)}
                ),
                AnonymizationStep(
                    method='k_anonymity',
                    target_columns=quasi_identifiers,
                    parameters={'k': parameters.get('k', 5)}
                ),
                AnonymizationStep(
                    method='t_closeness',
                    target_columns=sensitive_attributes,
                    parameters={
                        'l': parameters.get('l', 2),
                        't': parameters.get('t', 0.2)
                    }
                )
            ]
            privacy_target = {
                'k': parameters.get('k', 5),
                'l': parameters.get('l', 2),
                't': parameters.get('t', 0.2)
            }
            
        elif 'microaggregation' in method_key:
            steps = [
                AnonymizationStep(
                    method='microaggregation',
                    target_columns=quasi_identifiers,
                    parameters={'group_size': 3}
                )
            ]
            privacy_target = {'group_size': 3}
            
        elif 'pram' in method_key:
            steps = [
                AnonymizationStep(
                    method='pram',
                    target_columns=quasi_identifiers,
                    parameters={
                        'perturbation_rate': parameters.get('perturbation_rate', 0.05),
                        'seed': parameters.get('seed', 42)
                    }
                )
            ]
            privacy_target = {'perturbation_rate': parameters.get('perturbation_rate', 0.05)}
            
        else:
            # Default to k-anonymity
            steps = [
                AnonymizationStep(
                    method='k_anonymity',
                    target_columns=quasi_identifiers,
                    parameters={'k': parameters.get('k', 5)}
                )
            ]
            privacy_target = {'k': parameters.get('k', 5)}
        
        return AnonymizationPipeline(
            steps=steps,
            privacy_target=privacy_target,
            expected_privacy_level='High',
            expected_utility_impact='Medium',
            name=f"Single_{method_key.upper()}_k{parameters.get('k', 5)}"
        )
    
    def _create_hybrid_pipeline(
        self,
        method_combo: Tuple[str, str],
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        parameters: Dict[str, Any]
    ) -> AnonymizationPipeline:
        """Create a hybrid pipeline combining two methods."""
        method1, method2 = method_combo
        method1_key = method1.lower().replace('-', '_').replace(' ', '_')
        method2_key = method2.lower().replace('-', '_').replace(' ', '_')
        
        steps = []
        
        # Add generalization as foundation
        steps.append(
            AnonymizationStep(
                method='generalization',
                target_columns=quasi_identifiers,
                parameters={'generalization_level': parameters.get('generalization_level', 0.4)}
            )
        )
        
        # Add first method
        if 'k_anonymity' in method1_key:
            steps.append(AnonymizationStep(
                method='k_anonymity',
                target_columns=quasi_identifiers,
                parameters={'k': parameters.get('k', 5)}
            ))
        elif 'l_diversity' in method1_key:
            steps.append(AnonymizationStep(
                method='l_diversity',
                target_columns=sensitive_attributes,
                parameters={'l': parameters.get('l', 2)}
            ))
        
        # Add second method
        if 'l_diversity' in method2_key and 'l_diversity' not in method1_key:
            steps.append(AnonymizationStep(
                method='l_diversity',
                target_columns=sensitive_attributes,
                parameters={'l': parameters.get('l', 2)}
            ))
        elif 't_closeness' in method2_key:
            steps.append(AnonymizationStep(
                method='t_closeness',
                target_columns=sensitive_attributes,
                parameters={'t': parameters.get('t', 0.2)}
            ))
        
        privacy_target = {
            'k': parameters.get('k', 5),
            'l': parameters.get('l', 2),
            't': parameters.get('t', 0.2)
        }
        
        return AnonymizationPipeline(
            steps=steps,
            privacy_target=privacy_target,
            expected_privacy_level='Very High',
            expected_utility_impact='High',
            name=f"Hybrid_{method1_key.upper()}_{method2_key.upper()}"
        )
    
    def _create_rule_based_pipeline(
        self,
        rule_name: str,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        parameters: Dict[str, Any]
    ) -> AnonymizationPipeline:
        """Create a pipeline tailored to a specific rule."""
        rule_lower = rule_name.lower()
        
        if 'psu' in rule_lower:
            # PSU-specific pipeline
            steps = [
                AnonymizationStep(
                    method='psu_aggregation',
                    target_columns=quasi_identifiers,
                    parameters={'aggregation_level': 2}
                ),
                AnonymizationStep(
                    method='k_anonymity',
                    target_columns=quasi_identifiers,
                    parameters={'k': parameters.get('k', 5)}
                )
            ]
            privacy_target = {'k': parameters.get('k', 5)}
            name = "PSU_Specific_Pipeline"
            
        elif 'high cardinality' in rule_lower:
            # High cardinality requires strong generalization
            steps = [
                AnonymizationStep(
                    method='generalization',
                    target_columns=quasi_identifiers,
                    parameters={'generalization_level': 0.8}
                ),
                AnonymizationStep(
                    method='suppression',
                    target_columns=quasi_identifiers,
                    parameters={'suppress_ratio': 0.1}
                )
            ]
            privacy_target = {'suppress_ratio': 0.1}
            name = "HighCardinality_Pipeline"
            
        elif 'rare' in rule_lower:
            # Rare combinations - use suppression
            steps = [
                AnonymizationStep(
                    method='suppression',
                    target_columns=quasi_identifiers,
                    parameters={'rare_threshold': 5}
                ),
                AnonymizationStep(
                    method='k_anonymity',
                    target_columns=quasi_identifiers,
                    parameters={'k': parameters.get('k', 5)}
                )
            ]
            privacy_target = {'k': parameters.get('k', 5)}
            name = "RareCombinations_Pipeline"
            
        elif 'sensitive' in rule_lower or 'diversity' in rule_lower:
            # Sensitive attribute protection
            steps = [
                AnonymizationStep(
                    method='k_anonymity',
                    target_columns=quasi_identifiers,
                    parameters={'k': parameters.get('k', 5)}
                ),
                AnonymizationStep(
                    method='l_diversity',
                    target_columns=sensitive_attributes,
                    parameters={'l': parameters.get('l', 2)}
                )
            ]
            privacy_target = {'k': parameters.get('k', 5), 'l': parameters.get('l', 2)}
            name = "SensitiveAttribute_Pipeline"
            
        else:
            # Default rule-based pipeline
            steps = [
                AnonymizationStep(
                    method='k_anonymity',
                    target_columns=quasi_identifiers,
                    parameters={'k': parameters.get('k', 5)}
                )
            ]
            privacy_target = {'k': parameters.get('k', 5)}
            name = "Default_RuleBased_Pipeline"
        
        return AnonymizationPipeline(
            steps=steps,
            privacy_target=privacy_target,
            expected_privacy_level='High',
            expected_utility_impact='Medium',
            name=name
        )
    
    def _ensure_diversity(
        self,
        pipelines: List[AnonymizationPipeline],
        target_count: int
    ) -> List[AnonymizationPipeline]:
        """Ensure diversity in generated pipelines."""
        if len(pipelines) >= target_count:
            return pipelines[:target_count]
        
        # If we have fewer pipelines than target, generate more variations
        while len(pipelines) < target_count:
            # Create variation of existing pipeline
            if pipelines:
                base_pipeline = pipelines[len(pipelines) % len(pipelines)]
                # Slightly modify k value
                for step in base_pipeline.steps:
                    if 'k' in step.parameters:
                        step.parameters['k'] = min(step.parameters['k'] + 1, 15)
                pipelines.append(base_pipeline)
        
        return pipelines[:target_count]
    
    def get_generated_pipelines(self) -> List[AnonymizationPipeline]:
        """Get all generated pipelines."""
        return self.generated_pipelines
    
    def export_pipelines_to_dict(self) -> List[Dict[str, Any]]:
        """Export pipelines as dictionaries."""
        return [p.to_dict() for p in self.generated_pipelines]
