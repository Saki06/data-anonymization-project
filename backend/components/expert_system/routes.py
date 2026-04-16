"""
Expert System API Routes
Professional SDC anonymization expert system endpoints
"""

from fastapi import APIRouter, HTTPException, Form, Request
from typing import Optional, Dict, Any
import logging
import json
import pandas as pd
import numpy as np

# Import from sibling modules
from .knowledge_base import AnonymizationKnowledgeBase

router = APIRouter(prefix="/knowledge-base", tags=["Expert System"])
logger = logging.getLogger(__name__)

# Global knowledge base instance (will be injected from main.py)
_knowledge_base = None


def set_knowledge_base(kb: AnonymizationKnowledgeBase):
    """Set the knowledge base from main.py"""
    global _knowledge_base
    _knowledge_base = kb
    logger.info("Knowledge base initialized")


@router.get("/")
async def get_knowledge_base_info():
    """Get basic expert system information"""
    global _knowledge_base
    
    if _knowledge_base is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")
    
    methods = _knowledge_base.get_all_methods()
    rules = _knowledge_base.rules_engine.get_all_rules()
    
    return {
        "system": "Expert System for SDC Anonymization",
        "total_methods": len(methods),
        "total_rules": len(rules),
        "status": "operational"
    }


@router.get("/methods")
async def get_all_methods():
    """Get all available anonymization methods with details"""
    global _knowledge_base
    
    if _knowledge_base is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")
    
    methods = _knowledge_base.get_all_methods()
    return {
        "methods": methods,
        "count": len(methods),
        "categories": {
            "microdata_protection": ["k_anonymity", "l_diversity", "t_closeness"],
            "transformation": ["generalization", "suppression", "microaggregation"],
            "census_specific": ["psu_aggregation", "geo_generalization"],
            "advanced": ["differential_privacy", "synthetic_data"],
        }
    }


@router.get("/methods/{method_key}")
async def get_method_details(method_key: str):
    """Get detailed information about a specific SDC method"""
    global _knowledge_base
    
    if _knowledge_base is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")
    
    details = _knowledge_base.get_method_details(method_key)
    if not details:
        raise HTTPException(status_code=404, detail=f"Method '{method_key}' not found")
    
    return details


@router.get("/rules")
async def get_all_rules():
    """Get all expert system rules"""
    global _knowledge_base
    
    if _knowledge_base is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")
    
    rules = _knowledge_base.rules_engine.get_all_rules()
    return {
        "rules": [
            {
                "name": rule.name,
                "explanation": rule.explanation,
                "severity": rule.severity,
                "recommended_methods": rule.recommended_methods
            }
            for rule in rules
        ],
        "count": len(rules)
    }


@router.get("/rules/{rule_name}")
async def get_rule_details(rule_name: str):
    """Get details about a specific rule"""
    global _knowledge_base
    
    if _knowledge_base is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")
    
    rule_details = _knowledge_base.get_rule_details(rule_name)
    if not rule_details:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_name}' not found")
    
    return rule_details


@router.post("/recommend")
async def get_recommendations(profile: Dict[str, Any]):
    """
    Get SDC method recommendations based on data profile.
    
    Request body should contain profiling metrics from RiskAnalyzer:
    {
        "unique_ratio": 0.92,
        "min_group_size": 2,
        "has_psu": true,
        "sensitive_distinct": 2,
        "num_high_risk": 3,
        ...
    }
    
    Returns:
    {
        "primary_method": "...",
        "secondary_methods": [...],
        "hybrid_approach": bool,
        "overall_privacy_level": "...",
        "overall_utility_impact": "...",
        "recommendations": [...],
        "additional_notes": "..."
    }
    """
    global _knowledge_base
    
    if _knowledge_base is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")
    
    try:
        # Get recommendations as dict for API response
        recommendations = _knowledge_base.get_recommendations_dict(profile)
        
        # Add triggered rules for transparency
        triggered_rules = _knowledge_base.get_triggered_rules(profile)
        recommendations["triggered_rules"] = triggered_rules
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


@router.post("/feedback")
async def submit_ai_agent_feedback(feedback: Dict[str, str]):
    """
    Submit feedback from AI agents about method performance.
    
    Request body:
    {
        "method_key": "k_anonymity",
        "feedback": "Achieves 95% utility with excellent privacy guarantee"
    }
    """
    global _knowledge_base
    
    if _knowledge_base is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")
    
    try:
        method_key = feedback.get("method_key")
        feedback_text = feedback.get("feedback")
        
        if not method_key or not feedback_text:
            raise HTTPException(status_code=400, detail="method_key and feedback are required")
        
        _knowledge_base.add_ai_feedback(method_key, feedback_text)
        logger.info(f"Feedback recorded for method '{method_key}'")
        
        return {
            "status": "success",
            "message": f"Feedback recorded for method '{method_key}'"
        }
        
    except Exception as e:
        logger.error(f"Error recording feedback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error recording feedback: {str(e)}")


@router.get("/statistics")
async def get_recommendation_statistics():
    """Get statistics about recommendations made so far"""
    global _knowledge_base
    
    if _knowledge_base is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")
    
    stats = _knowledge_base.get_recommendation_statistics()
    return stats


# Global sessions storage (for execute endpoint)
_sessions = None


def set_sessions(sessions: Dict):
    """Set sessions from main.py"""
    global _sessions
    _sessions = sessions


@router.post("/execute")
async def execute_with_validation(
    session_id: str = Form(...),
    profile_json: Optional[str] = Form(None),
    parameters_json: Optional[str] = Form(None)
):
    """
    Execute recommended methods with full validation and constraint enforcement.
    
    This endpoint converts recommendations into enforced privacy by:
    1. Generating recommendations based on profile
    2. Executing transformations
    3. Validating constraints (k-anonymity, l-diversity, t-closeness)
    4. Iterating if violations occur
    
    Request body (Form data):
    - session_id: Session ID for the dataset
    - profile_json: Optional JSON string with profile metrics
    - parameters_json: Optional JSON string with execution parameters (k, l, t, generalization_level)
    
    Returns:
    {
        "success": bool,
        "applied_methods": [...],
        "parameters_used": {...},
        "validation_results": {...},
        "violations": [...],
        "iterations_performed": int,
        "final_k_value": int,
        "final_l_value": int,
        "final_t_value": float,
        "suppression_ratio": float,
        "sample_data": [...],
        "recommendations_used": {...}
    }
    """
    global _knowledge_base, _sessions
    
    if _knowledge_base is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")
    
    if _sessions is None or session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        session = _sessions[session_id]
        df = session['df']
        quasi_identifiers = session.get('quasi_identifiers', [])
        sensitive_attributes = session.get('sensitive_attributes', [])
        
        if not quasi_identifiers:
            raise HTTPException(status_code=400, detail="No quasi-identifiers selected")
        
        # Parse profile if provided
        profile = {}
        if profile_json:
            profile = json.loads(profile_json)
        
        # Parse parameters if provided
        parameters = {}
        if parameters_json:
            parameters = json.loads(parameters_json)

        # Execute using the internal execution engine so we can store the full anonymized DataFrame in-session.
        rec_set = _knowledge_base.recommend_methods(profile)
        execution_result = _knowledge_base.execution_engine.execute_with_validation(
            df=df,
            quasi_identifiers=quasi_identifiers,
            sensitive_attributes=sensitive_attributes,
            recommendations=rec_set,
            initial_params=parameters,
        )

        if execution_result.anonymized_data is not None:
            session["anonymized_df"] = execution_result.anonymized_data

        # Reuse knowledge_base serializer for response shape, but include full validation details.
        response = {
            "success": execution_result.success,
            "applied_methods": execution_result.applied_methods,
            "parameters_used": execution_result.parameters_used,
            "validation_results": execution_result.validation_results,
            "violations": execution_result.violations,
            "iterations_performed": execution_result.iterations_performed,
            "final_k_value": execution_result.final_k_value,
            "final_l_value": execution_result.final_l_value,
            "final_t_value": execution_result.final_t_value,
            "suppression_ratio": execution_result.suppression_ratio,
            "recommendations_used": {
                "primary_method": rec_set.primary_method,
                "secondary_methods": rec_set.secondary_methods,
                "hybrid_approach": rec_set.hybrid_approach,
                "overall_privacy_level": rec_set.overall_privacy_level,
                "overall_utility_impact": rec_set.overall_utility_impact,
            },
        }

        if execution_result.anonymized_data is not None:
            sample_data = execution_result.anonymized_data.head(20).to_dict("records")
            for record in sample_data:
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None
                    elif isinstance(value, (np.integer, np.floating)):
                        record[key] = float(value)
            response["sample_data"] = sample_data

        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing with validation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")


@router.post("/validate")
async def validate_constraints(
    session_id: str = Form(...)
):
    """
    Validate privacy constraints on already anonymized data.
    
    Returns validation results for k-anonymity, l-diversity, and t-closeness.
    """
    global _sessions
    
    if _sessions is None or session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        session = _sessions[session_id]
        original_df = session['df']
        anon_df = session.get('anonymized_df')
        quasi_identifiers = session.get('quasi_identifiers', [])
        sensitive_attributes = session.get('sensitive_attributes', [])
        
        if anon_df is None:
            raise HTTPException(status_code=400, detail="No anonymized data available. Run anonymization first.")
        
        if not quasi_identifiers:
            raise HTTPException(status_code=400, detail="No quasi-identifiers selected")
        
        # Use execution engine for validation
        from .execution_engine import AnonymizationExecutionEngine
        engine = AnonymizationExecutionEngine()
        
        validation_results = engine.validate_constraints_only(
            df=anon_df,
            original_df=original_df,
            quasi_identifiers=quasi_identifiers,
            sensitive_attributes=sensitive_attributes,
            k=5,  # Default values - could be parameterized
            l=2,
            t=0.2
        )
        
        # Convert to dict
        result = {}
        for constraint_name, validation_result in validation_results.items():
            result[constraint_name] = {
                "is_valid": validation_result.is_valid,
                "actual_value": validation_result.actual_value,
                "required_value": validation_result.required_value,
                "message": validation_result.message
            }
        
        return {
            "validation_results": result,
            "all_constraints_satisfied": all(v.is_valid for v in validation_results.values())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating constraints: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")