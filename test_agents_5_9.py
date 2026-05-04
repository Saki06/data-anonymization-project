"""
Test Suite for Agents 5-9 (Pipeline Generator, NSGA-II, Decision, Post-Validation)

Tests:
- Agent 5: Pipeline Generator
- Agent 6: NSGA-II Optimization
- Agent 7: Decision Agent
- Agent 9: Post-Validation Agent
"""

import sys
import os
import pandas as pd
import numpy as np

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from backend.components.expert_system.knowledge_base import AnonymizationKnowledgeBase
from backend.components.expert_system.pipeline_generator import PipelineGenerator
from backend.components.optimization.nsga2 import NSGA2PipelineOptimizer
from backend.components.expert_system.decision_and_validation_agent import DecisionAgent, PostValidationAgent
from backend.components.ai_agent.risk_analyzer import RiskAnalyzer


def create_test_dataset():
    """Create a test dataset for anonymization."""
    np.random.seed(42)
    n_records = 100
    
    data = {
        'age': np.random.randint(18, 80, n_records),
        'gender': np.random.choice(['M', 'F'], n_records),
        'zip_code': np.random.randint(10000, 99999, n_records),
        'occupation': np.random.choice(['Doctor', 'Teacher', 'Engineer', 'Manager'], n_records),
        'income': np.random.randint(20000, 150000, n_records),
        'health_condition': np.random.choice(['Healthy', 'Diabetes', 'Hypertension'], n_records)
    }
    
    return pd.DataFrame(data)


def test_agent5_pipeline_generator():
    """Test Agent 5: Pipeline Generator"""
    print("\n" + "="*80)
    print("TEST: AGENT 5 - PIPELINE GENERATOR")
    print("="*80)
    
    # Create test data
    df = create_test_dataset()
    quasi_identifiers = ['age', 'gender', 'zip_code']
    sensitive_attributes = ['income', 'health_condition']
    
    # Create recommendations (simulated)
    recommendations = {
        'primary_method': 'k_anonymity',
        'secondary_methods': ['l_diversity', 't_closeness'],
        'triggered_rules': ['High Cardinality in QI', 'Low Diversity in Sensitive Attribute']
    }
    
    # Generate pipelines
    generator = PipelineGenerator()
    pipelines = generator.generate_pipelines(
        recommendations=recommendations,
        quasi_identifiers=quasi_identifiers,
        sensitive_attributes=sensitive_attributes,
        dataset_size=len(df),
        num_pipelines=10
    )
    
    print(f"✓ Generated {len(pipelines)} anonymization pipelines")
    print("\nSample Pipelines:")
    for i, pipeline in enumerate(pipelines[:3]):
        print(f"\n  Pipeline {i}:")
        print(f"    Name: {pipeline.name}")
        print(f"    Privacy Target: {pipeline.privacy_target}")
        print(f"    Expected Privacy Level: {pipeline.expected_privacy_level}")
        print(f"    Steps:")
        for step in pipeline.steps:
            print(f"      - {step}")
    
    return pipelines


def test_agent6_nsga2_optimization(pipelines):
    """Test Agent 6: NSGA-II Optimization"""
    print("\n" + "="*80)
    print("TEST: AGENT 6 - NSGA-II OPTIMIZATION")
    print("="*80)
    
    df = create_test_dataset()
    quasi_identifiers = ['age', 'gender', 'zip_code']
    sensitive_attributes = ['income', 'health_condition']
    
    # Optimize pipelines
    optimizer = NSGA2PipelineOptimizer(population_size=10, n_generations=5)
    
    # Convert pipelines to dict format
    pipeline_dicts = [p.to_dict() for p in pipelines]
    
    results = optimizer.optimize_pipelines(
        df=df,
        pipelines=pipeline_dicts,
        quasi_identifiers=quasi_identifiers,
        sensitive_attributes=sensitive_attributes
    )
    
    print(f"✓ Optimization completed successfully")
    print(f"  Total pipelines evaluated: {results['total_pipelines']}")
    print(f"  Pareto front size: {results['pareto_front_size']}")
    print(f"  Optimization success: {results['optimization_success']}")
    
    if results['best_solution']:
        print(f"\n  Best Solution:")
        print(f"    Privacy Score: {results['best_solution']['privacy_score']:.4f}")
        print(f"    Utility Score: {results['best_solution']['utility_score']:.4f}")
        print(f"    Pipeline ID: {results['best_solution']['pipeline_id']}")
    
    print(f"\n  Pareto Front (Top 3):")
    for i, sol in enumerate(results['pareto_front'][:3]):
        print(f"    {i+1}. Pipeline {sol['pipeline_id']}: Privacy={sol['privacy_score']:.4f}, Utility={sol['utility_score']:.4f}")
    
    return results


def test_agent7_decision_agent(optimizer_results):
    """Test Agent 7: Decision Agent"""
    print("\n" + "="*80)
    print("TEST: AGENT 7 - DECISION AGENT (PARETO FRONT SELECTION)")
    print("="*80)
    
    decision_agent = DecisionAgent()
    
    # Extract data from optimization results
    all_results = optimizer_results['all_results']
    pipelines = [r['pipeline'] for r in all_results]
    privacy_scores = [r['privacy_score'] for r in all_results]
    utility_scores = [r['utility_score'] for r in all_results]
    
    # Evaluate Pareto front
    pareto_solutions = decision_agent.evaluate_pareto_front(
        pipelines=pipelines,
        privacy_scores=privacy_scores,
        utility_scores=utility_scores
    )
    
    print(f"✓ Pareto front evaluated: {len(pareto_solutions)} solutions")
    
    # Auto-select best solution
    best_solution = decision_agent.auto_select_best_solution(
        weight_privacy=0.6,
        weight_utility=0.4
    )
    
    print(f"\n✓ Auto-selected best solution:")
    print(f"  Pipeline ID: {best_solution.pipeline_id}")
    print(f"  Privacy Score: {best_solution.privacy_score:.4f}")
    print(f"  Utility Score: {best_solution.utility_score:.4f}")
    print(f"  Distance to Ideal: {best_solution.distance_to_ideal():.4f}")
    
    # Get selection rationale
    rationale = decision_agent.get_selection_rationale(best_solution)
    print(f"\n  Rationale: {rationale['rationale']}")
    
    # Test human-in-the-loop mode
    print(f"\n✓ Top 5 solutions for human selection:")
    user_options = decision_agent.get_pareto_front_for_user(top_k=5)
    for i, option in enumerate(user_options):
        print(f"  {i+1}. Pipeline {option['pipeline_id']}: Privacy={option['privacy_score']:.4f}, Utility={option['utility_score']:.4f}")
    
    return best_solution


def test_agent9_post_validation(best_solution):
    """Test Agent 9: Post-Validation Agent"""
    print("\n" + "="*80)
    print("TEST: AGENT 9 - POST-VALIDATION AGENT")
    print("="*80)
    
    # Create test data
    df = create_test_dataset()
    quasi_identifiers = ['age', 'gender', 'zip_code']
    sensitive_attributes = ['income', 'health_condition']
    
    # For testing, create a simple anonymized version
    # (In real scenario, this would be from the execution engine)
    anonymized_df = df.copy()
    anonymized_df['age'] = (anonymized_df['age'] // 10) * 10  # Generalize age
    anonymized_df['zip_code'] = anonymized_df['zip_code'] // 1000 * 1000  # Generalize zip
    
    # Validate
    post_validator = PostValidationAgent()
    validation_report = post_validator.validate_anonymized_data(
        anonymized_df=anonymized_df,
        original_df=df,
        quasi_identifiers=quasi_identifiers,
        sensitive_attributes=sensitive_attributes,
        required_k=5,
        required_l=2,
        required_t=0.2
    )
    
    print(f"✓ Post-validation completed")
    print(f"\n  Validation Results:")
    print(f"    Overall Valid: {validation_report.is_valid}")
    print(f"    k-anonymity Met: {validation_report.k_anonymity_met} (actual={validation_report.actual_k}, required={validation_report.required_k})")
    print(f"    l-diversity Met: {validation_report.l_diversity_met} (actual={validation_report.actual_l}, required={validation_report.required_l})")
    print(f"    t-closeness Met: {validation_report.t_closeness_met} (actual={validation_report.actual_t:.4f}, required={validation_report.required_t})")
    
    if validation_report.violations:
        print(f"\n  Violations Found: {len(validation_report.violations)}")
        for v in validation_report.violations:
            print(f"    - {v['message']}")
    
    if validation_report.remediation_actions:
        print(f"\n  Recommended Remediation Actions:")
        for action in validation_report.remediation_actions[:3]:
            print(f"    - {action}")
    
    print(f"\n  Re-optimization Needed: {validation_report.re_optimization_needed}")
    
    return validation_report


def test_knowledge_base_integration():
    """Test integration through knowledge base"""
    print("\n" + "="*80)
    print("TEST: KNOWLEDGE BASE INTEGRATION (ALL AGENTS)")
    print("="*80)
    
    # Initialize knowledge base
    knowledge_base = AnonymizationKnowledgeBase()
    
    # Create test data
    df = create_test_dataset()
    quasi_identifiers = ['age', 'gender', 'zip_code']
    sensitive_attributes = ['income', 'health_condition']
    
    # Generate profile
    risk_analyzer = RiskAnalyzer()
    profile = risk_analyzer.compute_risk_metrics(
        df=df,
        quasi_identifiers=quasi_identifiers,
        sensitive_attributes=sensitive_attributes
    )
    
    print(f"✓ Risk profile generated")
    if isinstance(profile, dict):
        k_anon = profile.get('k_anonymity', 'N/A')
        unique_ratio = profile.get('unique_ratio', 'N/A')
        print(f"  k-anonymity: {k_anon}")
        if isinstance(unique_ratio, (int, float)):
            print(f"  unique_ratio: {unique_ratio:.4f}")
        else:
            print(f"  unique_ratio: {unique_ratio}")
    else:
        profile = {} # treat as empty if unexpected format
        print(f"  Profile: {type(profile)} (converted to dict for processing)")
    
    # Get recommendations
    recommendations = knowledge_base.get_recommendations_dict(profile)
    print(f"\n✓ Recommendations generated")
    print(f"  Primary Method: {recommendations.get('primary_method')}")
    print(f"  Secondary Methods: {recommendations.get('secondary_methods')}")
    print(f"  Overall Privacy Level: {recommendations.get('overall_privacy_level')}")
    
    # Generate pipelines (Agent 5)
    pipelines = knowledge_base.generate_anonymization_pipelines(
        recommendations=recommendations,
        quasi_identifiers=quasi_identifiers,
        sensitive_attributes=sensitive_attributes,
        dataset_size=len(df),
        num_pipelines=10
    )
    print(f"\n✓ Agent 5 (Pipeline Generator): Generated {len(pipelines)} pipelines")
    
    # Test decision agent
    if pipelines:
        # Create dummy scores for testing
        privacy_scores = [np.random.uniform(0.3, 0.8) for _ in pipelines]
        utility_scores = [np.random.uniform(0.2, 0.7) for _ in pipelines]
        
        selection = knowledge_base.select_best_solution_from_pareto(
            pipelines=pipelines,
            privacy_scores=privacy_scores,
            utility_scores=utility_scores,
            mode='auto'
        )
        print(f"✓ Agent 7 (Decision Agent): Selected best solution")
        if 'selected_solution' in selection:
            print(f"  Selected Pipeline ID: {selection['selected_solution'].get('pipeline_id')}")
    
    # Test post-validation
    anonymized_df = df.copy()
    anonymized_df['age'] = (anonymized_df['age'] // 10) * 10
    
    validation = knowledge_base.post_validate_anonymization(
        anonymized_df=anonymized_df,
        original_df=df,
        quasi_identifiers=quasi_identifiers,
        sensitive_attributes=sensitive_attributes,
        required_k=5,
        required_l=2,
        required_t=0.2
    )
    print(f"✓ Agent 9 (Post-Validation): Validation completed")
    print(f"  Valid: {validation.get('is_valid')}")
    print(f"  Re-optimization Needed: {validation.get('re_optimization_needed')}")
    
    return knowledge_base


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("COMPREHENSIVE TEST SUITE: AGENTS 5-9")
    print("="*80)
    
    try:
        # Test Agent 5: Pipeline Generator
        pipelines = test_agent5_pipeline_generator()
        
        # Test Agent 6: NSGA-II Optimization
        optimizer_results = test_agent6_nsga2_optimization(pipelines)
        
        # Test Agent 7: Decision Agent
        best_solution = test_agent7_decision_agent(optimizer_results)
        
        # Test Agent 9: Post-Validation
        validation_report = test_agent9_post_validation(best_solution)
        
        # Test Knowledge Base Integration
        knowledge_base = test_knowledge_base_integration()
        
        print("\n" + "="*80)
        print("✓ ALL TESTS COMPLETED SUCCESSFULLY!")
        print("="*80)
        print("\nSummary:")
        print("  ✓ Agent 5 (Pipeline Generator): WORKING")
        print("  ✓ Agent 6 (NSGA-II Optimization): WORKING")
        print("  ✓ Agent 7 (Decision Agent): WORKING")
        print("  ✓ Agent 9 (Post-Validation Agent): WORKING")
        print("  ✓ Knowledge Base Integration: WORKING")
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
