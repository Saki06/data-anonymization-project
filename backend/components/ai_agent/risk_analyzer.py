"""
SDC Risk Analyzer - Privacy Risk Analysis Component
Computes comprehensive risk metrics from dataset for re-identification risk assessment.
This is the mandatory first stage in the SDC pipeline.

Responsibilities:
- Compute equivalence class sizes
- Compute prosecutor, journalist, marketer risks
- Compute uniqueness rates
- Compute attribute disclosure risk
- Compute linkage risk
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from collections import Counter
import math

# Import knowledge base from expert_system
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from backend.components.expert_system.knowledge_base import AnonymizationKnowledgeBase


class SDCRiskAnalyzer:
    """
    SDC Risk Analyzer - Computes comprehensive privacy risk metrics.
    
    Pipeline:
        Dataset
           ↓
        Risk Analyzer (this component)
           ↓
        Profile Metrics
           ↓
        Rules / Optimization
    """
    
    def __init__(self):
        self.knowledge_base = AnonymizationKnowledgeBase()
        self.detected_problems = []
        self.risk_metrics = {}
    
    def compute_risk_metrics(self, df: pd.DataFrame, quasi_identifiers: List[str],
                            sensitive_attributes: List[str] = None) -> Dict[str, Any]:
        """
        Compute comprehensive risk metrics from dataset.
        This is the mandatory first stage - computes metrics directly from data.
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            sensitive_attributes: List of sensitive attribute column names
            
        Returns:
            Dictionary with comprehensive risk metrics
        """
        self.detected_problems = []
        self.risk_metrics = {}
        
        # Validate inputs
        if df is None or len(df) == 0:
            return self._empty_risk_metrics()
        
        missing_qis = [qi for qi in quasi_identifiers if qi not in df.columns]
        if missing_qis:
            raise ValueError(f"Quasi-identifiers not found: {missing_qis}")
        
        sensitive_requested = list(sensitive_attributes or [])
        missing_sensitive = [c for c in sensitive_requested if c not in df.columns]
        for col in missing_sensitive:
            self.detected_problems.append({
                'problem': f'Sensitive attribute "{col}" not found in dataset columns',
                'condition': 'Column selected for SI analysis is missing from the uploaded data',
                'severity': 'Medium',
                'column': col,
                'type': 'sensitive_attribute_config',
            })
        sensitive_attributes = [c for c in sensitive_requested if c in df.columns]
        
        qi_df = df[quasi_identifiers].copy() if quasi_identifiers else pd.DataFrame()
        
        # === COMPUTE CORE RISK METRICS ===
        
        # 1. Equivalence Class Analysis
        equivalence_metrics = self._compute_equivalence_metrics(qi_df)
        
        # 2. Population Uniqueness & Uniqueness Rate
        uniqueness_metrics = self._compute_uniqueness_metrics(qi_df, df)
        
        # 3. Prosecutor Risk (risk of re-identifying a specific record)
        prosecutor_risk = self._compute_prosecutor_risk(qi_df)
        
        # 4. Journalist Risk (risk of finding someone in a small group)
        journalist_risk = self._compute_journalist_risk(qi_df)
        
        # 5. Marketer Risk (risk of characterizing a group)
        marketer_risk = self._compute_marketer_risk(qi_df, sensitive_attributes, df)
        
        # 6. Attribute Disclosure Risk
        attribute_disclosure_risk = self._compute_attribute_disclosure_risk(
            qi_df, sensitive_attributes, df
        )
        
        # 7. Linkage Risk
        linkage_risk = self._compute_linkage_risk(qi_df)
        
        # 8. Attribute Entropy
        attribute_entropy = self._compute_attribute_entropy(qi_df)
        
        # Combine all metrics
        self.risk_metrics = {
            # Core equivalence class metrics
            'min_group_size': equivalence_metrics['min_group_size'],
            'avg_group_size': equivalence_metrics['avg_group_size'],
            'max_group_size': equivalence_metrics['max_group_size'],
            'total_equivalence_classes': equivalence_metrics['total_equivalence_classes'],
            
            # Uniqueness metrics
            'unique_records_ratio': uniqueness_metrics['unique_records_ratio'],
            'population_uniqueness': uniqueness_metrics['population_uniqueness'],
            'sample_uniqueness': uniqueness_metrics['sample_uniqueness'],
            
            # Risk scores
            'prosecutor_risk': prosecutor_risk,
            'journalist_risk': journalist_risk,
            'marketer_risk': marketer_risk,
            'attribute_disclosure_risk': attribute_disclosure_risk,
            'linkage_risk': linkage_risk,
            
            # Entropy
            'attribute_entropy': attribute_entropy,
            
            # Additional metrics for rules engine
            'unique_ratio': uniqueness_metrics['max_unique_ratio'],
            'rare_combinations_ratio': equivalence_metrics['rare_combinations_ratio'],
            'num_qi': len(quasi_identifiers),
            'dataset_size': len(df),
            
            # For backward compatibility with rules_engine
            'min_group_size_compat': equivalence_metrics['min_group_size'],
            'avg_group_size_compat': equivalence_metrics['avg_group_size'],
            'unique_records_ratio_compat': uniqueness_metrics['unique_records_ratio'],
            'attribute_entropy_compat': attribute_entropy,
            'population_uniqueness_compat': uniqueness_metrics['population_uniqueness'],
        }
        
        # Build profile for rules engine
        profile = self._build_profile_for_rules(
            df=df,
            quasi_identifiers=quasi_identifiers,
            sensitive_attributes=sensitive_attributes,
            qi_df=qi_df
        )
        
        # Get triggered rules
        triggered_rules = self.knowledge_base.get_triggered_rules(profile)
        
        # Get recommendations
        recommendations = self.knowledge_base.get_recommendations_dict(profile)
        
        return {
            'risk_metrics': self.risk_metrics,
            'triggered_rules': triggered_rules,
            'recommendations': recommendations,
            'profile': profile,
            'detected_problems': self.detected_problems,
            'overall_risk_score': self._compute_overall_risk_score(),
            'sensitive_attributes_requested': sensitive_requested,
            'sensitive_attributes_used': sensitive_attributes,
            'sensitive_attributes_missing': missing_sensitive,
        }
    
    def _compute_equivalence_metrics(self, qi_df: pd.DataFrame) -> Dict[str, Any]:
        """Compute equivalence class size metrics."""
        if qi_df.empty or len(qi_df) == 0:
            return {
                'min_group_size': 0,
                'avg_group_size': 0,
                'max_group_size': 0,
                'total_equivalence_classes': 0,
                'rare_combinations_ratio': 0
            }
        
        # Group by QI combinations and get sizes
        equivalence_classes = qi_df.groupby(list(qi_df.columns)).size()
        
        min_size = int(equivalence_classes.min()) if len(equivalence_classes) > 0 else 0
        avg_size = float(equivalence_classes.mean()) if len(equivalence_classes) > 0 else 0
        max_size = int(equivalence_classes.max()) if len(equivalence_classes) > 0 else 0
        total_classes = len(equivalence_classes)
        
        # Rare combinations (< 5 records)
        rare_threshold = 5
        rare_count = (equivalence_classes < rare_threshold).sum()
        rare_ratio = rare_count / total_classes if total_classes > 0 else 0
        
        # Check for small equivalence classes (k-anonymity violation)
        if min_size < 5:
            self.detected_problems.append({
                'problem': 'Small Equivalence Classes',
                'condition': f'Minimum equivalence class size: {min_size} (< 5)',
                'severity': 'High',
                'min_size': min_size,
                'type': 'equivalence_class'
            })
        
        return {
            'min_group_size': min_size,
            'avg_group_size': avg_size,
            'max_group_size': max_size,
            'total_equivalence_classes': total_classes,
            'rare_combinations_ratio': rare_ratio
        }
    
    def _compute_uniqueness_metrics(self, qi_df: pd.DataFrame, 
                                    df: pd.DataFrame) -> Dict[str, Any]:
        """Compute uniqueness rate metrics."""
        if qi_df.empty or len(qi_df) == 0:
            return {
                'unique_records_ratio': 0,
                'population_uniqueness': 0,
                'sample_uniqueness': 0,
                'max_unique_ratio': 0
            }
        
        n = len(df)
        
        # Unique QI combinations ratio
        unique_combinations = qi_df.drop_duplicates().shape[0]
        unique_records_ratio = unique_combinations / n if n > 0 else 0
        
        # Population uniqueness (estimated from sample)
        # Using the Sanchez et al. method for population uniqueness estimation
        population_uniqueness = self._estimate_population_uniqueness(qi_df, n)
        
        # Sample uniqueness
        sample_uniqueness = unique_records_ratio
        
        # Max unique ratio across individual QIs
        max_unique_ratio = 0
        for col in qi_df.columns:
            unique_ratio = qi_df[col].nunique() / n
            max_unique_ratio = max(max_unique_ratio, unique_ratio)
        
        # Check for high uniqueness
        if unique_records_ratio > 0.05:
            self.detected_problems.append({
                'problem': 'High Unique Records',
                'condition': f'{unique_records_ratio:.1%} of records are unique',
                'severity': 'High',
                'unique_ratio': unique_records_ratio,
                'type': 'uniqueness'
            })
        
        return {
            'unique_records_ratio': unique_records_ratio,
            'population_uniqueness': population_uniqueness,
            'sample_uniqueness': sample_uniqueness,
            'max_unique_ratio': max_unique_ratio
        }
    
    def _estimate_population_uniqueness(self, qi_df: pd.DataFrame, 
                                        sample_size: int) -> float:
        """
        Estimate population uniqueness using the Zayatz method.
        This provides a more accurate estimate of re-identification risk.
        """
        if qi_df.empty or sample_size == 0:
            return 0
        
        # Get equivalence class sizes
        ec_sizes = qi_df.groupby(list(qi_df.columns)).size()
        
        if len(ec_sizes) == 0:
            return 0
        
        # Calculate E#2 (expected number of unique units in population)
        # Using the simplified Zayatz formula
        n = sample_size
        total_unique = 0
        
        for size in ec_sizes:
            if size == 1:
                # Singleton - high probability of being unique in population
                # Estimate using 1 - (1 - 1/N)^n where N is population
                # For simplicity, we use a scaling factor
                total_unique += 1 * (1 - math.pow((n - 1) / n, n))
            elif size == 2:
                total_unique += 0.5 * (1 - math.pow((n - 2) / n, n))
            else:
                # For larger groups, probability of uniqueness is very low
                total_unique += 1.0 / size
        
        # Normalize to ratio
        estimated_population_unique = min(1.0, total_unique / n)
        
        return estimated_population_unique
    
    def _compute_prosecutor_risk(self, qi_df: pd.DataFrame) -> float:
        """
        Compute Prosecutor Risk.
        This is the probability of re-identification for a specific target record
        when the attacker knows the person is in the dataset.
        
        Prosecutor risk = 1 / average_equivalence_class_size
        Higher risk when equivalence classes are small.
        """
        if qi_df.empty or len(qi_df) == 0:
            return 0
        
        ec_sizes = qi_df.groupby(list(qi_df.columns)).size()
        
        if len(ec_sizes) == 0:
            return 0
        
        # Risk is based on the fraction of records in smallest groups
        # Records in groups of size 1 have 100% risk
        # Records in groups of size k have 1/k risk
        
        total_records = len(qi_df)
        weighted_risk = 0
        
        for size in ec_sizes:
            prob = size / total_records
            risk = 1.0 / size if size > 0 else 0
            weighted_risk += prob * risk
        
        # Normalize to 0-1 scale (cap at 1)
        return min(1.0, weighted_risk * 10)  # Scale up for visibility
    
    def _compute_journalist_risk(self, qi_df: pd.DataFrame) -> float:
        """
        Compute Journalist Risk.
        This is the risk that an attacker can find a small group (e.g., < k)
        that could be targeted for re-identification.
        
        Higher risk when there are many small equivalence classes.
        """
        if qi_df.empty or len(qi_df) == 0:
            return 0
        
        ec_sizes = qi_df.groupby(list(qi_df.columns)).size()
        
        if len(ec_sizes) == 0:
            return 0
        
        total_records = len(qi_df)
        
        # Risk based on fraction of records in small groups (< k)
        k_threshold = 5
        small_group_records = (ec_sizes[ec_sizes <= k_threshold]).sum()
        
        journalist_risk = small_group_records / total_records if total_records > 0 else 0
        
        return journalist_risk
    
    def _compute_marketer_risk(self, qi_df: pd.DataFrame, 
                               sensitive_attributes: List[str],
                               df: pd.DataFrame) -> float:
        """
        Compute Marketer Risk (Inference Risk).
        This is the risk of learning sensitive information about a group
        based on the quasi-identifiers.
        
        Higher risk when there's high correlation between QIs and sensitive attrs.
        """
        if qi_df.empty or len(qi_df) == 0:
            return 0
        
        # Base risk on uniqueness
        ec_sizes = qi_df.groupby(list(qi_df.columns)).size()
        
        # Calculate Gini-Simpson index for equivalence classes
        n = len(qi_df)
        if n <= 1:
            return 0
        
        proportions = ec_sizes / n
        gini_simpson = 1 - (proportions ** 2).sum()
        
        # Adjust based on sensitive attributes if present
        if sensitive_attributes:
            # Check for l-diversity violation
            l_threshold = 2
            for sens_attr in sensitive_attributes:
                if sens_attr in df.columns:
                    for name, group in df.groupby(list(qi_df.columns)):
                        if len(group) > 0:
                            distinct_sens = group[sens_attr].nunique()
                            if distinct_sens < l_threshold:
                                # High inference risk for this group
                                return min(1.0, gini_simpson + 0.3)
        
        return min(1.0, gini_simpson)
    
    def _compute_attribute_disclosure_risk(self, qi_df: pd.DataFrame,
                                           sensitive_attributes: List[str],
                                           df: pd.DataFrame) -> float:
        """
        Compute Attribute Disclosure Risk.
        This is the risk that an attacker can learn sensitive attributes
        for a group of people based on their quasi-identifiers.
        """
        if not sensitive_attributes or df.empty:
            return 0
        
        max_disclosure_risk = 0
        
        for sens_attr in sensitive_attributes:
            if sens_attr not in df.columns:
                continue
            
            if qi_df.empty:
                continue
            
            # For each equivalence class, check diversity of sensitive attribute
            for name, group in df.groupby(list(qi_df.columns)):
                if len(group) > 0:
                    distinct_values = group[sens_attr].nunique()
                    
                    # If only 1 distinct value in group, high disclosure risk
                    if distinct_values == 1:
                        group_size = len(group)
                        # Risk increases with group size
                        disclosure_prob = min(1.0, group_size / 10)
                        max_disclosure_risk = max(max_disclosure_risk, disclosure_prob)
        
        return max_disclosure_risk
    
    def _compute_linkage_risk(self, qi_df: pd.DataFrame) -> float:
        """
        Compute Linkage Risk.
        This is the risk of linking records across different datasets
        based on quasi-identifiers.
        """
        if qi_df.empty or len(qi_df) == 0:
            return 0
        
        # Linkage risk is higher when:
        # 1. More unique combinations
        # 2. Higher cardinality in QIs
        
        n = len(qi_df)
        unique_combinations = qi_df.drop_duplicates().shape[0]
        
        # Basic linkage risk from uniqueness
        uniqueness_risk = unique_combinations / n if n > 0 else 0
        
        # Adjust by number of QIs (more QIs = more linkage points = higher risk)
        num_qis = len(qi_df.columns)
        qi_multiplier = min(2.0, 1 + (num_qis - 1) * 0.1)  # Cap at 2x
        
        linkage_risk = min(1.0, uniqueness_risk * qi_multiplier)
        
        return linkage_risk
    
    def _compute_attribute_entropy(self, qi_df: pd.DataFrame) -> float:
        """
        Compute average attribute entropy.
        Higher entropy means more uncertainty/higher re-identification risk.
        """
        if qi_df.empty:
            return 0
        
        total_entropy = 0
        n = len(qi_df)
        
        for col in qi_df.columns:
            value_counts = qi_df[col].value_counts()
            proportions = value_counts / n
            
            # Shannon entropy
            entropy = -(proportions * np.log2(proportions + 1e-10)).sum()
            total_entropy += entropy
        
        # Average entropy across all QIs
        avg_entropy = total_entropy / len(qi_df.columns) if len(qi_df.columns) > 0 else 0
        
        return avg_entropy
    
    def _compute_overall_risk_score(self) -> float:
        """Compute overall risk score from individual metrics."""
        if not self.risk_metrics:
            return 0
        
        # Weight different risk components
        weights = {
            'prosecutor_risk': 0.25,
            'journalist_risk': 0.20,
            'marketer_risk': 0.15,
            'attribute_disclosure_risk': 0.20,
            'linkage_risk': 0.20
        }
        
        overall = 0
        for risk_type, weight in weights.items():
            risk_value = self.risk_metrics.get(risk_type, 0)
            overall += risk_value * weight
        
        return min(1.0, overall)
    
    def _build_profile_for_rules(self, df: pd.DataFrame, 
                                  quasi_identifiers: List[str],
                                  sensitive_attributes: List[str],
                                  qi_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Build comprehensive profile with ALL metrics expected by rules_engine.
        Uses computed risk metrics from this analyzer.
        """
        # PSU metrics - only check in QIs, not all columns
        has_psu = self._check_psu_present(df, quasi_identifiers)
        
        profile = {
            # Basic dataset info
            'dataset_size': len(df),
            'total_records': len(df),
            'num_qi': len(quasi_identifiers),
            'total_qis': len(quasi_identifiers),
            
            # === Metrics from Risk Analyzer (computed directly from data) ===
            'min_group_size': self.risk_metrics.get('min_group_size', 0),
            'avg_group_size': self.risk_metrics.get('avg_group_size', 0),
            'unique_records_ratio': self.risk_metrics.get('unique_records_ratio', 0),
            'population_uniqueness': self.risk_metrics.get('population_uniqueness', 0),
            'attribute_entropy': self.risk_metrics.get('attribute_entropy', 0),
            
            # === Metrics for rules engine (computed) ===
            'unique_ratio': self.risk_metrics.get('max_unique_ratio', 0),
            'rare_combinations_ratio': self.risk_metrics.get('rare_combinations_ratio', 0),
            
            # K-anonymity related
            'k_threshold': 5,
            
            # Cardinality metrics
            'num_continuous_qi': self._count_continuous_qi(df, quasi_identifiers),
            'high_cardinality_numeric': self._check_high_cardinality_numeric(df, quasi_identifiers),
            
            # Sensitive attribute metrics
            'sensitive_distinct': self._get_min_sensitive_distinct(df, sensitive_attributes),
            'sensitive_max_freq': self._get_max_sensitive_freq(df, sensitive_attributes),
            
            # Correlation
            'max_qi_correlation': self._get_max_qi_correlation(qi_df, quasi_identifiers),
            
            # Outliers
            'outliers_detected': self._check_outliers_present(qi_df, quasi_identifiers),
            
            # PSU metrics - fixed logic (only trigger if PSU is in QIs)
            'has_psu': has_psu,
            'psu_at_release': has_psu,
            
            # Geographic
            'has_geographic_qi': self._check_geographic_qi_present(quasi_identifiers),
            'geographic_precision': self._get_geographic_precision(df, quasi_identifiers),
            
            # Household
            'is_household_data': self._check_household_data(df),
            
            # Temporal - check for actual date/time columns in QIs, not just keyword matching
            'has_temporal_qi': self._check_temporal_qi_present(quasi_identifiers, df),
            'temporal_patterns': False,  # Disable by default, only enable if actual temporal analysis shows patterns
            
            # Risk scores
            'prosecutor_risk': self.risk_metrics.get('prosecutor_risk', 0),
            'journalist_risk': self.risk_metrics.get('journalist_risk', 0),
            'marketer_risk': self.risk_metrics.get('marketer_risk', 0),
            'linkage_risk': self.risk_metrics.get('linkage_risk', 0),
            
            # Policy-driven
            'dp_required': False,
            'synthetic_suitable': self._check_synthetic_suitable(df, quasi_identifiers),
            
            # Risk counts
            'num_high_risk': sum(1 for p in self.detected_problems 
                                if p.get('severity') in ('High', 'Critical')),
            
            # Additional metrics
            'categorical_risk_score': self._calculate_categorical_risk_score(df, quasi_identifiers),
            'has_categorical_qi': self._has_categorical_columns(df, quasi_identifiers),
            'sampling_allowed': True,
            
            # Rare values ratio for local suppression rule
            'rare_values_ratio': self._calculate_rare_values_ratio(df, quasi_identifiers),
            
            # Identifier detection
            'identifier_present': self._check_identifiers_present(df, quasi_identifiers),
            
            # Store detected problems
            'detected_problems': self.detected_problems,
        }
        
        return profile
    
    def _count_continuous_qi(self, df: pd.DataFrame, qis: List[str]) -> int:
        """Count number of continuous/numeric QIs"""
        count = 0
        for qi in qis:
            if qi in df.columns and pd.api.types.is_numeric_dtype(df[qi]):
                count += 1
        return count
    
    def _check_high_cardinality_numeric(self, df: pd.DataFrame, qis: List[str]) -> bool:
        """Check if any numeric QI has high cardinality"""
        for qi in qis:
            if qi in df.columns and pd.api.types.is_numeric_dtype(df[qi]):
                unique_ratio = df[qi].nunique() / len(df)
                if unique_ratio > 0.5:
                    return True
        return False
    
    def _get_min_sensitive_distinct(self, df: pd.DataFrame, sensitive_attrs: List[str]) -> int:
        """Get minimum distinct count across all sensitive attributes"""
        if not sensitive_attrs:
            return 100
        min_distinct = float('inf')
        for attr in sensitive_attrs:
            if attr in df.columns:
                distinct = df[attr].nunique()
                min_distinct = min(min_distinct, distinct)
        return int(min_distinct) if min_distinct != float('inf') else 100
    
    def _get_max_sensitive_freq(self, df: pd.DataFrame, sensitive_attrs: List[str]) -> float:
        """Get maximum frequency ratio for sensitive attributes"""
        if not sensitive_attrs:
            return 0.0
        max_freq = 0.0
        for attr in sensitive_attrs:
            if attr in df.columns:
                value_counts = df[attr].value_counts()
                if len(value_counts) > 0:
                    freq = value_counts.iloc[0] / len(df)
                    max_freq = max(max_freq, freq)
        return max_freq
    
    def _get_max_qi_correlation(self, qi_df: pd.DataFrame, qis: List[str]) -> float:
        """Get maximum absolute correlation between numeric QIs"""
        numeric_qis = qi_df.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_qis) < 2:
            return 0.0
        corr_matrix = qi_df[numeric_qis].corr()
        max_corr = 0.0
        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                corr_val = abs(corr_matrix.iloc[i, j])
                if not np.isnan(corr_val):
                    max_corr = max(max_corr, corr_val)
        return max_corr
    
    def _check_outliers_present(self, qi_df: pd.DataFrame, qis: List[str]) -> bool:
        """Check if any numeric QIs have outliers"""
        numeric_qis = qi_df.select_dtypes(include=[np.number]).columns.tolist()
        for qi in numeric_qis:
            if qi in qi_df.columns:
                values = qi_df[qi].dropna()
                if len(values) > 0:
                    mean = values.mean()
                    std = values.std()
                    if std > 0:
                        z_scores = np.abs((values - mean) / std)
                        outlier_ratio = (z_scores > 3).sum() / len(values)
                        if outlier_ratio > 0.05:
                            return True
        return False
    
    def _check_psu_present(self, df: pd.DataFrame, quasi_identifiers: List[str] = None) -> bool:
        """Check if PSU column is present in QIs (not just any column)"""
        # Only check in QIs, not all columns - PSU risk only applies if it's selected as QI
        columns_to_check = quasi_identifiers if quasi_identifiers else []
        if not columns_to_check:
            return False
        
        psu_keywords = ['psu', 'primary_sampling', 'sampling_unit', 'cluster', 
                       'enumeration', 'ea', 'enum_area']
        for col in columns_to_check:
            col_lower = col.lower().replace('_', '').replace(' ', '')
            if any(keyword.replace('_', '') in col_lower for keyword in psu_keywords):
                return True
        return False
    
    def _check_geographic_qi_present(self, qis: List[str]) -> bool:
        """Check if any QI is geographic"""
        geo_keywords = ['address', 'location', 'city', 'zip', 'postal', 'lat', 'lon', 'coordinate']
        for qi in qis:
            if any(keyword in qi.lower() for keyword in geo_keywords):
                return True
        return False
    
    def _get_geographic_precision(self, df: pd.DataFrame, qis: List[str]) -> str:
        """Get geographic precision level"""
        geo_keywords = ['address', 'location', 'lat', 'lon', 'coordinate']
        for qi in qis:
            if qi in df.columns:
                if any(keyword in qi.lower() for keyword in geo_keywords):
                    return 'exact'
        return 'district'
    
    def _check_household_data(self, df: pd.DataFrame) -> bool:
        """Check if dataset appears to be household data"""
        household_keywords = ['household', 'household_id', 'hh_id', 'dwelling', 'family']
        for col in df.columns:
            col_lower = col.lower().replace('_', '').replace(' ', '')
            if any(keyword.replace('_', '') in col_lower for keyword in household_keywords):
                return True
        return False
    
    def _check_temporal_qi_present(self, qis: List[str], df: pd.DataFrame = None) -> bool:
        """Check if any QI is temporal - requires actual date/time column or specific keywords"""
        if df is None or df.empty or not qis:
            return False
        
        temporal_keywords = ['date', 'time', 'year', 'month', 'day', 'birth', 'dob']
        for qi in qis:
            # First check if column is a datetime type
            if qi in df.columns and hasattr(df[qi], 'dt'):
                try:
                    if pd.api.types.is_datetime64_any_dtype(df[qi]):
                        return True
                except:
                    pass
            # Then check keywords in column name
            if any(keyword in qi.lower() for keyword in temporal_keywords):
                return True
        return False
    
    def _check_synthetic_suitable(self, df: pd.DataFrame, qis: List[str]) -> bool:
        """Check if synthetic data generation is suitable"""
        if len(df) < 1000:
            return False
        if len(qis) > 10:
            return True
        return False
    
    def _calculate_categorical_risk_score(self, df: pd.DataFrame, qis: List[str]) -> float:
        """
        Calculate risk score for categorical QIs.
        
        For categorical variables, high re-identification risk occurs when:
        1. The number of unique categories is relatively high compared to dataset size
        2. OR the combination of categorical QIs creates many unique patterns
        
        Returns a score from 0-1 where higher = more risk.
        """
        if not qis:
            return 0.0
        
        # Find categorical columns among QIs
        categorical_qis = []
        for qi in qis:
            if qi in df.columns:
                # Check if column is categorical (object type or low cardinality numeric)
                if df[qi].dtype == 'object' or df[qi].dtype.name == 'category':
                    categorical_qis.append(qi)
                elif pd.api.types.is_numeric_dtype(df[qi]):
                    # Also check if numeric has low cardinality (might be coded categorical)
                    unique_ratio = df[qi].nunique() / len(df)
                    if unique_ratio < 0.1:  # Less than 10% unique = likely categorical
                        categorical_qis.append(qi)
        
        if not categorical_qis:
            return 0.0
        
        # Calculate risk based on categorical QI characteristics
        max_risk = 0.0
        
        for qi in categorical_qis:
            n_unique = df[qi].nunique()
            n_total = len(df)
            unique_ratio = n_unique / n_total if n_total > 0 else 0
            
            # Risk factors for categorical data:
            # 1. High cardinality relative to sample (but not so high it's continuous)
            # 2. Moderate cardinality with combination potential
            
            if n_unique > 1:
                # Calculate risk based on categories and combinations
                # More categories = more identifying power = higher risk
                # We use a log scale because very high cardinality (like names) 
                # would be handled differently (suppression/hashing)
                
                # Factor 1: Category ratio (how many categories vs total records)
                # Moderate ratios (1-20%) indicate categorical data that could identify
                if unique_ratio < 0.01:
                    # Very rare categories - risk is moderate
                    risk1 = 0.3
                elif unique_ratio < 0.05:
                    # Few categories - low to moderate risk
                    risk1 = 0.4
                elif unique_ratio < 0.2:
                    # Moderate categories - highest risk for re-identification
                    risk1 = 0.8
                else:
                    # Many categories - treat more like quasi-continuous
                    risk1 = min(1.0, unique_ratio * 2)
                
                # Factor 2: Absolute number of categories (more categories = more identifying)
                if n_unique <= 3:
                    risk2 = 0.3  # Very few categories - limited identifying power
                elif n_unique <= 10:
                    risk2 = 0.6  # Moderate - good for PRAM
                elif n_unique <= 50:
                    risk2 = 0.8  # Many categories - high identifying power
                else:
                    risk2 = 1.0  # Very many - could be quasi-identifier
                
                # Combined risk for this QI
                qi_risk = (risk1 + risk2) / 2
                max_risk = max(max_risk, qi_risk)
        
        return max_risk
    
    def _has_categorical_columns(self, df: pd.DataFrame, qis: List[str]) -> bool:
        """Check if any QI is categorical (object/string type)."""
        for qi in qis:
            if qi in df.columns:
                if df[qi].dtype == 'object' or df[qi].dtype.name == 'category':
                    return True
        return False
    
    def _check_identifiers_present(self, df: pd.DataFrame, qis: List[str]) -> bool:
        """Check if direct identifiers are present"""
        id_keywords = ['id', 'name', 'ssn', 'social_security', 'email', 'phone', 
                     'address', 'national_id', 'passport', 'license']
        for col in df.columns:
            col_lower = col.lower().replace('_', '').replace(' ', '')
            if any(keyword.replace('_', '') in col_lower for keyword in id_keywords):
                return True
        return False
    
    def _calculate_rare_values_ratio(self, df: pd.DataFrame, qis: List[str]) -> float:
        """
        Calculate the ratio of rare values in quasi-identifiers.
        
        Rare values are those that appear less than a threshold (e.g., 5 times or 5% of data).
        This metric is used for the Local Suppression rule.
        
        Returns:
            Float between 0-1 representing the ratio of values that are rare
        """
        if not qis or df.empty:
            return 0.0
        
        total_cells = 0
        rare_cells = 0
        
        # Threshold for rare values (use 5 or 5% of data, whichever is smaller)
        threshold = min(5, max(1, len(df) * 0.05))
        
        for qi in qis:
            if qi not in df.columns:
                continue
            
            # Get value counts for this column
            value_counts = df[qi].value_counts()
            
            # Count rare values (frequency below threshold)
            rare_count = (value_counts < threshold).sum()
            
            total_cells += len(value_counts)
            rare_cells += rare_count
        
        if total_cells == 0:
            return 0.0
        
        return rare_cells / total_cells
    
    def _empty_risk_metrics(self) -> Dict[str, Any]:
        """Return empty risk metrics structure."""
        return {
            'risk_metrics': {
                'min_group_size': 0,
                'avg_group_size': 0,
                'unique_records_ratio': 0,
                'population_uniqueness': 0,
                'prosecutor_risk': 0,
                'journalist_risk': 0,
                'marketer_risk': 0,
                'attribute_disclosure_risk': 0,
                'linkage_risk': 0,
                'attribute_entropy': 0
            },
            'triggered_rules': [],
            'recommendations': None,
            'profile': {},
            'detected_problems': [],
            'overall_risk_score': 0
        }



# Keep backward compatibility with old RiskAnalyzer name
class RiskAnalyzer(SDCRiskAnalyzer):
    """Backward compatibility alias for SDCRiskAnalyzer."""
    
    def analyze_dataset(self, df: pd.DataFrame, quasi_identifiers: List[str], 
                       sensitive_attributes: List[str] = None) -> Dict[str, Any]:
        """
        Analyze dataset for re-identification risks (backward compatible method).
        This method provides backward compatibility with the old RiskAnalyzer API.
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            sensitive_attributes: List of sensitive attribute column names
            
        Returns:
            Dictionary with analysis results and recommendations
        """
        # Use the new compute_risk_metrics method
        result = self.compute_risk_metrics(df, quasi_identifiers, sensitive_attributes)
        
        # Convert to the old format expected by the analyze endpoint
        return {
            'risk_score': result.get('overall_risk_score', 0),
            'detected_problems': result.get('detected_problems', []),
            'statistics': {
                'total_records': len(df),
                'total_qis': len(quasi_identifiers),
                'unique_combinations': result.get('risk_metrics', {}).get('total_equivalence_classes', 0),
                'min_equivalence_class_size': result.get('risk_metrics', {}).get('min_group_size', 0),
                'avg_equivalence_class_size': result.get('risk_metrics', {}).get('avg_group_size', 0)
            },
            'recommendations': result.get('recommendations'),
            'triggered_rules': result.get('triggered_rules', []),
            'risk_metrics': result.get('risk_metrics', {}),
            # Expose the full rules profile for downstream optimization/execution.
            'profile': result.get('profile', {}),
            'sensitive_attributes_requested': result.get('sensitive_attributes_requested', []),
            'sensitive_attributes_used': result.get('sensitive_attributes_used', []),
            'sensitive_attributes_missing': result.get('sensitive_attributes_missing', []),
        }
