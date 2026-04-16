"""
Anonymization API Routes
Handles analysis, anonymization, comparison, and download endpoints
Quasi-identifier selection is handled by the quasi_selection component

Also includes Generalization Hierarchy Management endpoints for scientific SDC
"""

from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional, Dict, Any
import pandas as pd
import numpy as np
import json

# Import from sibling modules
from .methods import AnonymizationMethods, get_hierarchy_mgr
from .hierarchy_templates import get_default_templates, detect_attribute_type

router = APIRouter(prefix="", tags=["Anonymization"])

# Global storage for sessions (will be injected from main.py)
_sessions = {}


def set_sessions(sessions: Dict):
    """Set the sessions dictionary from main.py"""
    global _sessions
    _sessions = sessions


def set_components(components: Dict):
    """Set the components (risk_analyzer, knowledge_base, nsga2_optimizer) from main.py"""
    global _risk_analyzer, _knowledge_base, _nsga2_optimizer
    _risk_analyzer = components.get('risk_analyzer')
    _knowledge_base = components.get('knowledge_base')
    _nsga2_optimizer = components.get('nsga2_optimizer')


def _safe_params(op: dict, n_rows: int) -> dict:
    """Scale NSGA-II suggested params to dataset size so constraints are achievable."""
    k_raw  = int(op.get("k", 5))
    k_max  = max(2, min(20, max(1, n_rows // 100)))  # ~1% of rows, min 2, max 20
    k_safe = min(k_raw, k_max)

    l_raw  = int(op.get("l", 2))
    l_max  = max(2, min(5, max(1, int(k_safe ** 0.5))))
    l_safe = min(l_raw, l_max)

    t_raw  = float(op.get("t", 0.2))
    t_safe = max(0.15, min(0.5, t_raw))

    return {
        "k": k_safe,
        "l": l_safe,
        "t": round(t_safe, 3),
        "generalization_level": op.get("generalization_level", 0.5),
    }


@router.post("/analyze")
async def analyze_dataset(session_id: str = Form(...)):
    """
    Analyze dataset for re-identification risks and get recommendations
    """
    global _sessions, _risk_analyzer, _nsga2_optimizer
    
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _sessions[session_id]
    df = session['df']
    quasi_identifiers = session['quasi_identifiers']
    sensitive_attributes = session.get('sensitive_attributes', [])
    
    if not quasi_identifiers:
        raise HTTPException(status_code=400, detail="Please select quasi-identifiers first")
    
    if not _risk_analyzer or not _nsga2_optimizer:
        raise HTTPException(status_code=500, detail="Components not initialized")
    
    try:
        # Run risk analysis
        analysis_results = _risk_analyzer.analyze_dataset(
            df, quasi_identifiers, sensitive_attributes
        )
        
        # Run NSGA-II optimization for optimal parameters
        optimization_results = _nsga2_optimizer.optimize(
            df, quasi_identifiers, sensitive_attributes
        )
        
        # Combine results
        n_rows = len(df)
        raw_op = optimization_results.get('optimal_parameters', {})
        safe_op = _safe_params(raw_op, n_rows)
        analysis_results['optimal_parameters'] = safe_op
        analysis_results['row_count'] = n_rows
        analysis_results['optimization_results'] = {
            'pareto_front_size': len(optimization_results['pareto_front']),
            'optimization_success': optimization_results['optimization_success'],
            # F: [disclosure_risk, utility_loss]
            'pareto_front': optimization_results.get('pareto_front', [])
        }
        
        # Extract triggered_rules from recommendations if present (for frontend display)
        if analysis_results.get('recommendations') and isinstance(analysis_results['recommendations'], dict):
            analysis_results['triggered_rules'] = analysis_results['recommendations'].get('triggered_rules', [])
        
        # Store results
        session['analysis_results'] = analysis_results
        session['profile'] = analysis_results.get('profile', {}) or {}
        session['optimal_parameters'] = safe_op
        
        return analysis_results
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.post("/anonymize")
async def anonymize_data(
    session_id: str = Form(...),
    methods: Optional[str] = Form(None),  # JSON object with method parameters
    use_recommended: str = Form("true"),  # Accept as string, convert to bool
    anon_method: str = Form("hierarchy")  # hierarchy or traditional
):
    """
    Apply anonymization methods to the dataset
    """
    global _sessions
    
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _sessions[session_id]
    df = session['df']
    quasi_identifiers = session['quasi_identifiers']
    sensitive_attributes = session.get('sensitive_attributes', [])
    analysis_results = session.get('analysis_results')
    
    if not quasi_identifiers:
        raise HTTPException(status_code=400, detail="Please select quasi-identifiers first")
    
    try:
        # Convert string to boolean
        use_recommended_bool = use_recommended.lower() == "true"
        use_hierarchy = anon_method.lower() == "hierarchy"
        
        # CRITICAL: Handle PSU columns first if detected
        detected_problems = analysis_results.get('detected_problems', []) if analysis_results else []
        psu_columns = []
        
        for problem in detected_problems:
            if 'PSU' in problem.get('problem', ''):
                psu_col = problem.get('column')
                if psu_col and psu_col in df.columns:
                    psu_columns.append(psu_col)
        
        # Apply PSU handling before other anonymization
        anon_df = df.copy()
        for psu_col in psu_columns:
            # Check if there's a region/district column
            region_keywords = ['region', 'district', 'province', 'state', 'area']
            region_col = None
            for col in df.columns:
                if any(keyword in col.lower() for keyword in region_keywords):
                    region_col = col
                    break
            
            # Apply PSU handling (prefer aggregation if region exists, else random recode)
            method = 'aggregate' if region_col else 'random_recode'
            anon_df = AnonymizationMethods.handle_psu(
                anon_df, psu_col, method=method, region_column=region_col, min_group_size=5
            )
        
        # Resolve parameters
        if use_recommended_bool:
            params = (analysis_results or {}).get('optimal_parameters', {}) or session.get('optimal_parameters', {}) or {}
        else:
            params = json.loads(methods) if methods else {}
        k = int(params.get('k', 5))
        l = int(params.get('l', 2))
        t = float(params.get('t', 0.2))
        gen_level = float(params.get('generalization_level', 0.5))
        max_hierarchy_level = int(params.get('max_hierarchy_level', 4))
        forced_primary_method = params.get("forced_primary_method")

        # Professional path: execute + validate (enforced constraints)
        if not _knowledge_base:
            raise HTTPException(status_code=500, detail="Knowledge base not initialized")

        profile = session.get('profile') or (analysis_results or {}).get('profile') or {}
        rec_set = _knowledge_base.recommend_methods(profile)

        execution_result = _knowledge_base.execution_engine.execute_with_validation(
            df=anon_df,
            quasi_identifiers=quasi_identifiers,
            sensitive_attributes=sensitive_attributes,
            recommendations=rec_set,
            initial_params={
                "k": k,
                "l": l,
                "t": t,
                "generalization_level": gen_level,
                "generalization_strategy": "hierarchy" if use_hierarchy else "traditional",
                "max_hierarchy_level": max_hierarchy_level,
                "forced_primary_method": forced_primary_method,
            },
        )

        if execution_result.anonymized_data is None:
            raise HTTPException(status_code=500, detail="Execution engine returned no anonymized data")

        anon_df = execution_result.anonymized_data
        
        # Store anonymized data
        session['anonymized_df'] = anon_df
        session['execution_result'] = {
            "success": execution_result.success,
            "applied_methods": execution_result.applied_methods,
            "parameters_used": execution_result.parameters_used,
            "validation_results": execution_result.validation_results,
            "violations": execution_result.violations,
            "iterations_performed": execution_result.iterations_performed,
            "suppression_ratio": execution_result.suppression_ratio,
            "recommendations_used": {
                "primary_method": rec_set.primary_method,
                "secondary_methods": rec_set.secondary_methods,
                "hybrid_approach": rec_set.hybrid_approach,
                "overall_privacy_level": rec_set.overall_privacy_level,
                "overall_utility_impact": rec_set.overall_utility_impact,
            },
        }
        
        # Calculate anonymization metrics
        existing_qis = [qi for qi in quasi_identifiers if qi in anon_df.columns]
        if not existing_qis:
            existing_qis = list(anon_df.columns)[:len(quasi_identifiers)] if len(anon_df.columns) > 0 else []
        
        if existing_qis:
            qi_df = anon_df[existing_qis]
            suppressed = (qi_df == '*').sum().sum()
            total = len(qi_df) * len(existing_qis)
            suppression_ratio = suppressed / total if total > 0 else 0
            
            try:
                groups = qi_df.groupby(list(existing_qis))
                group_sizes = groups.size()
                min_size = int(group_sizes.min()) if len(group_sizes) > 0 else 0
                avg_size = float(group_sizes.mean()) if len(group_sizes) > 0 else 0
            except Exception:
                min_size = 0
                avg_size = 0
        else:
            suppression_ratio = 0
            min_size = 0
            avg_size = 0
        
        # Prepare sample data
        sample_data = anon_df.head(20).to_dict('records')
        for record in sample_data:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
                elif isinstance(value, (np.integer, np.floating)):
                    record[key] = float(value)
                elif isinstance(value, np.ndarray):
                    record[key] = value.tolist()
                elif isinstance(value, (pd.Timestamp, pd.DatetimeTZDtype)):
                    record[key] = str(value)
        
        return {
            "message": "Anonymization completed successfully",
            "method_used": "execution_engine_hierarchy" if use_hierarchy else "execution_engine_traditional",
            "parameters_used": {
                "k": k,
                "l": l,
                "t": t,
                "generalization_level": gen_level,
                "max_hierarchy_level": max_hierarchy_level,
            },
            "metrics": {
                "suppression_ratio": round(float(suppression_ratio), 3),
                "min_equivalence_class_size": min_size,
                "avg_equivalence_class_size": round(float(avg_size), 2),
                "total_records": len(anon_df),
                "total_columns": len(anon_df.columns)
            },
            "validation": session.get("execution_result", {}).get("validation_results", {}),
            "violations": session.get("execution_result", {}).get("violations", []),
            "applied_methods": session.get("execution_result", {}).get("applied_methods", []),
            "recommendations_used": session.get("execution_result", {}).get("recommendations_used", {}),
            "sample_data": sample_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Anonymization error: {error_detail}")
        raise HTTPException(status_code=500, detail=f"Anonymization error: {str(e)}")


@router.get("/download-anonymized")
async def download_anonymized(session_id: str, format: str = "csv"):
    """
    Download anonymized dataset
    """
    global _sessions
    
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _sessions[session_id]
    anon_df = session.get('anonymized_df')
    
    if anon_df is None:
        raise HTTPException(status_code=400, detail="No anonymized data available. Please run anonymization first.")
    
    try:
        if format == "csv":
            output_path = f"temp_anon_{session_id}.csv"
            anon_df.to_csv(output_path, index=False)
            return FileResponse(
                output_path,
                filename=f"anonymized_data_{session_id}.csv",
                media_type="text/csv"
            )
        elif format == "excel":
            output_path = f"temp_anon_{session_id}.xlsx"
            anon_df.to_excel(output_path, index=False)
            return FileResponse(
                output_path,
                filename=f"anonymized_data_{session_id}.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid format. Use 'csv' or 'excel'")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare")
async def compare_datasets(session_id: str = Form(...)):
    """
    Compare original and anonymized datasets
    Also computes post-anonymization risk metrics for comparison
    """
    global _sessions, _risk_analyzer
    
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _sessions[session_id]
    original_df = session['df']
    anonymized_df = session.get('anonymized_df')
    quasi_identifiers = session.get('quasi_identifiers', [])
    sensitive_attributes = session.get('sensitive_attributes', [])
    
    if anonymized_df is None:
        raise HTTPException(status_code=400, detail="No anonymized data available. Please run anonymization first.")
    
    if len(anonymized_df) == 0:
        raise HTTPException(status_code=400, detail="Anonymized dataset is empty. Anonymization may not have completed properly.")
    
    try:
        # Import risk analyzer for post-risk analysis
        from ..ai_agent.risk_analyzer import SDCRiskAnalyzer
        
        # Compute pre-anonymization risk metrics if not already available
        pre_risk_metrics = None
        if _risk_analyzer and quasi_identifiers:
            try:
                pre_analysis = _risk_analyzer.compute_risk_metrics(
                    original_df, quasi_identifiers, sensitive_attributes
                )
                pre_risk_metrics = pre_analysis.get('risk_metrics', {})
            except Exception as e:
                print(f"[WARN] Could not compute pre-risk metrics: {e}")
        
        # Compute post-anonymization risk metrics
        post_risk_metrics = None
        if _risk_analyzer and quasi_identifiers:
            try:
                post_analysis = _risk_analyzer.compute_risk_metrics(
                    anonymized_df, quasi_identifiers, sensitive_attributes
                )
                post_risk_metrics = post_analysis.get('risk_metrics', {})
            except Exception as e:
                print(f"[WARN] Could not compute post-risk metrics: {e}")
        
        # Prepare anonymized sample data
        anonymized_sample = []
        try:
            sample_df = anonymized_df.head(20)
            if len(sample_df) > 0:
                anonymized_sample = sample_df.to_dict('records')
                for record in anonymized_sample:
                    for key, value in record.items():
                        if pd.isna(value):
                            record[key] = None
                        elif isinstance(value, (np.integer, np.floating)):
                            record[key] = float(value)
                        elif isinstance(value, np.ndarray):
                            record[key] = value.tolist()
                        elif isinstance(value, (pd.Timestamp, pd.DatetimeTZDtype)):
                            record[key] = str(value)
                        else:
                            record[key] = str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value
            else:
                anonymized_sample = []
        except Exception as e:
            print(f"[ERROR] Error preparing sample: {e}")
            anonymized_sample = []
        
        comparison_results = {
            "original_shape": [int(original_df.shape[0]), int(original_df.shape[1])],
            "anonymized_shape": [int(anonymized_df.shape[0]), int(anonymized_df.shape[1])],
            "columns": original_df.columns.tolist(),
            "quasi_identifiers": quasi_identifiers,
            "sensitive_attributes": sensitive_attributes,
            "column_comparison": [],
            "sample_comparison": [],
            "statistics_comparison": {},
            "anonymized_sample": anonymized_sample,
            # Post-risk analysis comparison
            "risk_comparison": {
                "pre_risk_metrics": pre_risk_metrics,
                "post_risk_metrics": post_risk_metrics,
                "improvement": {}
            }
        }
        
        # Calculate risk improvement metrics
        if pre_risk_metrics and post_risk_metrics:
            comparison_results["risk_comparison"]["improvement"] = {
                "prosecutor_risk_reduction": max(0, (pre_risk_metrics.get('prosecutor_risk', 0) - post_risk_metrics.get('prosecutor_risk', 0))),
                "journalist_risk_reduction": max(0, (pre_risk_metrics.get('journalist_risk', 0) - post_risk_metrics.get('journalist_risk', 0))),
                "unique_records_reduction": max(0, (pre_risk_metrics.get('unique_records_ratio', 0) - post_risk_metrics.get('unique_records_ratio', 0))),
                "overall_risk_reduction": max(0, (pre_risk_metrics.get('linkage_risk', 0) - post_risk_metrics.get('linkage_risk', 0)))
            }
        
        # Compare each column
        for col in original_df.columns:
            if col in anonymized_df.columns:
                orig_col = original_df[col]
                anon_col = anonymized_df[col]
                
                col_info = {
                    "column_name": col,
                    "is_quasi_identifier": col in quasi_identifiers,
                    "is_sensitive_attribute": col in sensitive_attributes,
                    "original_unique": int(orig_col.nunique()),
                    "anonymized_unique": int(anon_col.nunique()),
                    "original_null": int(orig_col.isna().sum()),
                    "anonymized_null": int(anon_col.isna().sum()),
                    "data_type": str(orig_col.dtype),
                    "changes_detected": False,
                    "suppressed_values": 0,
                    "generalized_values": 0
                }
                
                # Check for suppressed values
                if anon_col.dtype == 'object':
                    suppressed = (anon_col == '*').sum()
                    col_info["suppressed_values"] = int(suppressed)
                    if suppressed > 0:
                        col_info["changes_detected"] = True
                    
                    # Check for generalized values (e.g., "20-29", "Range_1", etc.)
                    generalized = anon_col.str.contains(r'^\d+-\d+|Range_|Level_|Bin_', regex=True, na=False).sum()
                    col_info["generalized_values"] = int(generalized)
                    if generalized > 0:
                        col_info["changes_detected"] = True
                
                # Check if values changed
                if orig_col.dtype == anon_col.dtype:
                    changed = (orig_col != anon_col).sum()
                    col_info["changed_values"] = int(changed)
                    if changed > 0:
                        col_info["changes_detected"] = True
                
                comparison_results["column_comparison"].append(col_info)
        
        # Generate sample side-by-side comparison (first 10 rows)
        sample_rows = min(10, len(original_df))
        for idx in range(sample_rows):
            row_comparison = {
                "row_index": idx,
                "original": {},
                "anonymized": {},
                "differences": []
            }
            
            for col in original_df.columns:
                orig_val = original_df.iloc[idx][col]
                anon_val = anonymized_df.iloc[idx][col] if col in anonymized_df.columns else None
                
                # Convert to JSON-serializable format
                if pd.isna(orig_val):
                    orig_val_display = None
                elif isinstance(orig_val, (np.integer, np.floating)):
                    orig_val_display = float(orig_val)
                else:
                    orig_val_display = str(orig_val)
                
                if pd.isna(anon_val):
                    anon_val_display = None
                elif isinstance(anon_val, (np.integer, np.floating)):
                    anon_val_display = float(anon_val)
                else:
                    anon_val_display = str(anon_val)
                
                row_comparison["original"][col] = orig_val_display
                row_comparison["anonymized"][col] = anon_val_display
                
                # Track differences for QIs
                if col in quasi_identifiers and orig_val_display != anon_val_display:
                    row_comparison["differences"].append(col)
            
            comparison_results["sample_comparison"].append(row_comparison)
        
        # Overall statistics
        if quasi_identifiers:
            orig_qi_combinations = original_df[quasi_identifiers].drop_duplicates().shape[0]
            anon_qi_combinations = anonymized_df[quasi_identifiers].drop_duplicates().shape[0]
            
            comparison_results["statistics_comparison"] = {
                "original_unique_qi_combinations": orig_qi_combinations,
                "anonymized_unique_qi_combinations": anon_qi_combinations,
                "combination_reduction": float((1 - anon_qi_combinations/orig_qi_combinations) * 100) if orig_qi_combinations > 0 else 0,
                "total_qi_cells": len(original_df) * len(quasi_identifiers),
                "suppressed_qi_cells": int(((anonymized_df[quasi_identifiers] == '*').sum().sum())),
                "modified_qi_rows": int((anonymized_df[quasi_identifiers] != original_df[quasi_identifiers]).any(axis=1).sum())
            }
        
        return comparison_results
    
    except Exception as e:
        import traceback
        print(f"Comparison error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Comparison error: {str(e)}")


# ==================== HIERARCHY MANAGEMENT ENDPOINTS ====================

@router.get("/hierarchy/templates")
async def get_hierarchy_templates():
    """
    Get available hierarchy templates for common attribute types.
    
    Returns:
        Dictionary of available hierarchy templates
    """
    try:
        templates = get_default_templates()
        # Simplify for frontend
        result = {}
        for name, template in templates.items():
            result[name] = {
                'description': template.get('description', ''),
                'levels': len(template.get('levels', [])),
                'attribute_type': template.get('attribute_type', name)
            }
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting templates: {str(e)}")


@router.get("/hierarchy/detect")
async def detect_column_types(session_id: str):
    """
    Detect appropriate hierarchy types for quasi-identifiers in a session.
    
    Args:
        session_id: The session ID
        
    Returns:
        Dictionary mapping columns to detected types
    """
    global _sessions
    
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _sessions[session_id]
    df = session.get('df')
    quasi_identifiers = session.get('quasi_identifiers', [])
    
    if df is None or not quasi_identifiers:
        raise HTTPException(status_code=400, detail="No data or quasi-identifiers found")
    
    try:
        result = {}
        for qi in quasi_identifiers:
            if qi in df.columns:
                sample = df[qi].dropna().head(100).tolist()
                attr_type = detect_attribute_type(qi, sample)
                result[qi] = {
                    'detected_type': attr_type,
                    'has_template': attr_type in get_default_templates() if attr_type else False,
                    'sample_values': df[qi].unique()[:5].tolist() if len(df[qi].unique()) > 0 else []
                }
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting types: {str(e)}")


@router.post("/hierarchy/anonymize")
async def anonymize_with_hierarchy(
    session_id: str = Form(...),
    k: int = Form(5),
    use_hierarchy: str = Form("true")
):
    """
    Apply k-anonymity using hierarchical generalization.
    
    This endpoint uses the scientifically acceptable hierarchical generalization
    approach instead of ad-hoc pd.cut() or rare value grouping.
    
    Args:
        session_id: The session ID
        k: k-anonymity parameter
        use_hierarchy: Whether to use hierarchy-based generalization
        
    Returns:
        Anonymized data and metrics
    """
    global _sessions
    
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _sessions[session_id]
    df = session['df']
    quasi_identifiers = session['quasi_identifiers']
    
    if not quasi_identifiers:
        raise HTTPException(status_code=400, detail="Please select quasi-identifiers first")
    
    try:
        use_hierarchy_bool = use_hierarchy.lower() == "true"
        
        if use_hierarchy_bool:
            # Use hierarchy-based approach
            anon_df, info = AnonymizationMethods.k_anonymity_with_hierarchy(
                df, quasi_identifiers, k=k, max_hierarchy_level=4
            )
            
            # Also apply l-diversity and t-closeness if sensitive attributes exist
            sensitive_attributes = session.get('sensitive_attributes', [])
            if sensitive_attributes:
                for sens_attr in sensitive_attributes:
                    if sens_attr in anon_df.columns:
                        anon_df = AnonymizationMethods.l_diversity(
                            anon_df, quasi_identifiers, sens_attr, l=2
                        )
        else:
            # Use traditional approach
            anon_df = AnonymizationMethods.k_anonymity(df, quasi_identifiers, k=k)
            info = {'method': 'traditional'}
        
        # Store anonymized data
        session['anonymized_df'] = anon_df
        
        # Calculate metrics
        existing_qis = [qi for qi in quasi_identifiers if qi in anon_df.columns]
        if existing_qis:
            qi_df = anon_df[existing_qis]
            suppressed = (qi_df == '*').sum().sum()
            total = len(qi_df) * len(existing_qis)
            suppression_ratio = suppressed / total if total > 0 else 0
            
            try:
                groups = qi_df.groupby(list(existing_qis))
                group_sizes = groups.size()
                min_size = int(group_sizes.min()) if len(group_sizes) > 0 else 0
                avg_size = float(group_sizes.mean()) if len(group_sizes) > 0 else 0
            except Exception:
                min_size = 0
                avg_size = 0
        else:
            suppression_ratio = 0
            min_size = 0
            avg_size = 0
        
        # Prepare sample data
        sample_data = anon_df.head(20).to_dict('records')
        for record in sample_data:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
                elif isinstance(value, (np.integer, np.floating)):
                    record[key] = float(value)
                elif isinstance(value, np.ndarray):
                    record[key] = value.tolist()
                elif isinstance(value, (pd.Timestamp, pd.DatetimeTZDtype)):
                    record[key] = str(value)
        
        return {
            "message": "Anonymization with hierarchy completed",
            "method": "hierarchy_based" if use_hierarchy_bool else "traditional",
            "parameters_used": {
                "k": k,
                "use_hierarchy": use_hierarchy_bool
            },
            "hierarchy_info": info if use_hierarchy_bool else {},
            "metrics": {
                "suppression_ratio": round(float(suppression_ratio), 3),
                "min_equivalence_class_size": min_size,
                "avg_equivalence_class_size": round(float(avg_size), 2),
                "total_records": len(anon_df),
                "total_columns": len(anon_df.columns)
            },
            "sample_data": sample_data
        }
    
    except Exception as e:
        import traceback
        print(f"Hierarchy anonymization error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Anonymization error: {str(e)}")
