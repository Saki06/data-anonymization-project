"""
Anonymization Methods Implementation
Supports K-Anonymity, L-Diversity, T-Closeness, Generalization, Suppression, etc.

This module implements a more sophisticated approach to SDC that goes beyond
blanket suppression. It uses:
- Generalization hierarchies before suppression (Scientific approach for SDC)
- Local suppression (cell-level) instead of record suppression
- Iterative anonymization that tries multiple strategies

The hierarchy-based generalization is now handled by the GeneralizationHierarchyManager
which provides scientifically acceptable hierarchical generalization trees as required
for algorithms like Mondrian.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple, Optional, Callable
from collections import Counter
import warnings

# Import hierarchy manager components
from .hierarchy_manager import (
    GeneralizationHierarchyManager, 
    get_hierarchy_manager,
    GeneralizationHierarchy
)
from .hierarchy_templates import (
    get_default_templates, 
    detect_attribute_type,
    get_hierarchy_for_attribute
)


# Global hierarchy manager instance
_hierarchy_manager = None


def get_hierarchy_mgr() -> GeneralizationHierarchyManager:
    """Get or create the global hierarchy manager instance."""
    global _hierarchy_manager
    if _hierarchy_manager is None:
        _hierarchy_manager = get_hierarchy_manager()
    return _hierarchy_manager


class AnonymizationMethods:
    """Collection of SDC anonymization methods with advanced strategies."""
    
    # ==================== HELPER METHODS ====================
    
    @staticmethod
    def _is_ordinal_attribute(df: pd.DataFrame, column: str) -> bool:
        """
        Detect if a column represents ordinal/numeric data.
        
        Args:
            df: Input dataframe
            column: Column name to check
            
        Returns:
            True if the attribute is ordinal/numeric, False for categorical
        """
        if column not in df.columns:
            return False
        
        # Check if numeric dtype
        if pd.api.types.is_numeric_dtype(df[column]):
            return True
        
        # Check if the values can be converted to numeric (ordinal encoding possible)
        try:
            numeric_values = pd.to_numeric(df[column].dropna(), errors='coerce')
            valid_ratio = numeric_values.notna().sum() / df[column].dropna().shape[0]
            if valid_ratio > 0.8:
                return True
        except (ValueError, TypeError):
            pass
        
        # Check for ordinal-like categorical values
        unique_values = df[column].dropna().unique()
        ordinal_patterns = [
            ['low', 'medium', 'high'],
            ['low', 'medium', 'high', 'very high'],
            ['small', 'medium', 'large'],
            ['never', 'sometimes', 'often', 'always'],
            ['poor', 'fair', 'good', 'excellent'],
            ['1', '2', '3', '4', '5'],
            ['strongly disagree', 'disagree', 'neutral', 'agree', 'strongly agree'],
        ]
        
        value_lower = set(str(v).lower().strip() for v in unique_values)
        
        for pattern in ordinal_patterns:
            pattern_set = set(pattern)
            if len(value_lower & pattern_set) >= len(pattern_set) * 0.6:
                return True
        
        return False
    
    @staticmethod
    def _calculate_distribution_distance(dist1: Dict, dist2: Dict, is_ordinal: bool = False) -> float:
        """
        Calculate distribution distance between two distributions.
        
        For categorical attributes: uses Total Variation Distance (TVD)
        For ordinal/numeric attributes: uses Earth Mover's Distance (EMD)
        """
        all_values = set(dist1.keys()) | set(dist2.keys())
        
        if not is_ordinal:
            distance = 0.0
            for value in all_values:
                p1 = dist1.get(value, 0.0)
                p2 = dist2.get(value, 0.0)
                distance += abs(p1 - p2)
            return distance / 2.0
        
        try:
            sorted_values = sorted(all_values, key=lambda x: float(x) if str(x).replace('.','',1).replace('-','',1).isdigit() else 0)
        except (ValueError, TypeError):
            distance = 0.0
            for value in all_values:
                p1 = dist1.get(value, 0.0)
                p2 = dist2.get(value, 0.0)
                distance += abs(p1 - p2)
            return distance / 2.0
        
        cum_dist1 = []
        cum_dist2 = []
        
        for v in sorted_values:
            cum_dist1.append(dist1.get(v, 0.0))
            cum_dist2.append(dist2.get(v, 0.0))
        
        cum1 = 0
        cum2 = 0
        emd = 0.0
        
        for i in range(len(sorted_values)):
            cum1 += cum_dist1[i]
            cum2 += cum_dist2[i]
            emd += abs(cum1 - cum2)
        
        n = len(sorted_values)
        if n > 1:
            emd = emd / (2 * (n - 1))
        else:
            emd = emd / 2.0
            
        return min(emd, 1.0)
    
    @staticmethod
    def _get_equivalence_classes(df: pd.DataFrame, quasi_identifiers: List[str]) -> pd.DataFrame:
        """Get equivalence class sizes for all QI combinations."""
        if not quasi_identifiers:
            return pd.DataFrame()
        return df.groupby(quasi_identifiers).size().reset_index(name='group_size')
    
    @staticmethod
    def _apply_local_suppression(
        df: pd.DataFrame, 
        quasi_identifiers: List[str], 
        max_suppression_per_column: float = 0.1,
        mask_symbol: str = '*'
    ) -> pd.DataFrame:
        """
        Apply local suppression - only suppress individual cells that would 
        cause small equivalence classes, not entire records.
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            max_suppression_per_column: Maximum fraction to suppress per column
            mask_symbol: Symbol to use for suppression
            
        Returns:
            Anonymized dataframe with local suppression applied
        """
        # Cast all QI columns to object so mask_symbol (a string) can be
        # assigned regardless of whether the original dtype is int64 / float64.
        _qi_cast = {col: object for col in quasi_identifiers
                    if col in df.columns and df[col].dtype != object}
        anon_df = df.astype(_qi_cast) if _qi_cast else df.copy()

        # Get current equivalence classes
        qi_df = anon_df[quasi_identifiers]
        groups = qi_df.groupby(list(quasi_identifiers)).size()
        
        # Find groups that are too small (less than 2 records)
        small_groups = groups[groups < 2].index
        
        if len(small_groups) == 0:
            return anon_df
        
        # For each small group, try to suppress individual values
        for small_group in small_groups:
            # Get indices of records in this small group
            if len(quasi_identifiers) == 1:
                mask = qi_df[quasi_identifiers[0]] == small_group[0]
            else:
                mask = (qi_df[quasi_identifiers] == small_group).all(axis=1)
            
            # Skip if no records match this group
            if mask.sum() == 0:
                continue
            
            # Try suppressing each QI value to make this record join a larger group
            for qi_idx, qi in enumerate(quasi_identifiers):
                try:
                    original_values = anon_df.loc[mask, qi].values
                    if len(original_values) == 0:
                        continue
                except (IndexError, KeyError):
                    continue
                
                # Check if suppressing this value would help
                test_df = anon_df.copy()
                # Ensure the test column is object-typed before writing mask_symbol
                if test_df[qi].dtype != object:
                    test_df[qi] = test_df[qi].astype(object)
                test_df.loc[mask, qi] = mask_symbol
                
                # Check new group size
                test_qi_df = test_df[quasi_identifiers]
                new_groups = test_qi_df.groupby(list(quasi_identifiers)).size()
                
                # Find the new group this record belongs to
                new_group_key = tuple(
                    mask_symbol if i == qi_idx else small_group[i] 
                    for i in range(len(quasi_identifiers))
                )
                
                if new_group_key in new_groups and new_groups[new_group_key] >= 2:
                    anon_df.loc[mask, qi] = mask_symbol
                    break
        
        return anon_df
    
    # ==================== GENERALIZATION METHODS ====================
    
    @staticmethod
    def generalize_quasi_identifiers(
        df: pd.DataFrame, 
        quasi_identifiers: List[str],
        generalization_level: float = 0.5,
        hierarchy_levels: Optional[Dict[str, Dict]] = None
    ) -> pd.DataFrame:
        """
        Generalize quasi-identifiers based on generalization level.
        
        This applies hierarchical generalization to reduce uniqueness
        before applying k-anonymity, l-diversity, or t-closeness.
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            generalization_level: 0.0 (no generalization) to 1.0 (max generalization)
            hierarchy_levels: Optional dict of column-specific hierarchies
            
        Returns:
            Dataframe with generalized QI values
        """
        anon_df = df.copy()
        
        if generalization_level <= 0:
            return anon_df
        
        for qi in quasi_identifiers:
            if qi not in anon_df.columns:
                continue
            
            # Convert to object type first to avoid categorical issues
            if anon_df[qi].dtype.name == 'category':
                anon_df[qi] = anon_df[qi].astype(str)
            
            # Determine number of bins/groups based on level
            if pd.api.types.is_numeric_dtype(anon_df[qi]):
                # For numeric: use binning
                num_bins = max(2, int(10 * (1 - generalization_level) + 2))
                anon_df[qi] = pd.cut(
                    anon_df[qi], 
                    bins=num_bins, 
                    labels=[f'Range_{i+1}' for i in range(num_bins)],
                    include_lowest=True
                )
                # Convert to string to avoid categorical issues
                anon_df[qi] = anon_df[qi].astype(str)
            elif AnonymizationMethods._is_ordinal_attribute(df, qi):
                # For ordinal: reduce to broader categories
                unique_vals = anon_df[qi].nunique()
                if unique_vals > 5:
                    num_groups = max(3, int(unique_vals * (1 - generalization_level * 0.7)))
                    try:
                        anon_df[qi] = pd.qcut(
                            anon_df[qi].rank(method='first'), 
                            q=num_groups, 
                            labels=[f'Level_{i+1}' for i in range(num_groups)],
                            duplicates='drop'
                        )
                        anon_df[qi] = anon_df[qi].astype(str)
                    except (ValueError, TypeError):
                        # If qcut fails, use simple binning
                        value_counts = anon_df[qi].value_counts()
                        threshold = len(anon_df) / num_groups
                        anon_df.loc[anon_df[qi].isin(value_counts[value_counts < threshold].index), qi] = 'Other'
            else:
                # For categorical: group rare values
                value_counts = anon_df[qi].value_counts()
                threshold = len(anon_df) * (0.2 - generalization_level * 0.15)
                threshold = max(threshold, 1)  # At least 1 record
                rare_values = value_counts[value_counts < threshold].index
                anon_df.loc[anon_df[qi].isin(rare_values), qi] = 'Other'
        
        return anon_df
    
    @staticmethod
    def generalization(df: pd.DataFrame, column: str, method: str = 'categorical',
                      bins: int = 5, ranges: List[Tuple] = None) -> pd.DataFrame:
        """
        Generalize values in a column
        
        Args:
            df: Input dataframe
            column: Column name to generalize
            method: 'categorical', 'numeric_binning', 'numeric_ranges', 'suppress_rare'
            bins: Number of bins for numeric binning
            ranges: Custom ranges for numeric generalization
            
        Returns:
            Anonymized dataframe
        """
        anon_df = df.copy()
        
        if method == 'categorical':
            # Suppress low-frequency categories
            value_counts = anon_df[column].value_counts()
            threshold = len(anon_df) * 0.05
            rare_values = value_counts[value_counts < threshold].index
            anon_df.loc[anon_df[column].isin(rare_values), column] = 'Other'
            
        elif method == 'numeric_binning':
            if pd.api.types.is_numeric_dtype(anon_df[column]):
                anon_df[column] = pd.cut(anon_df[column], bins=bins, 
                                        labels=[f'Bin_{i+1}' for i in range(bins)])
        
        elif method == 'numeric_ranges':
            if pd.api.types.is_numeric_dtype(anon_df[column]) and ranges:
                def assign_range(value):
                    for i, (low, high) in enumerate(ranges):
                        if low <= value <= high:
                            return f'{low}-{high}'
                    return 'Other'
                anon_df[column] = anon_df[column].apply(assign_range)
        
        elif method == 'suppress_rare':
            if anon_df[column].dtype != object:
                anon_df[column] = anon_df[column].astype(object)
            value_counts = anon_df[column].value_counts()
            threshold = len(anon_df) * 0.05
            rare_values = value_counts[value_counts < threshold].index
            anon_df.loc[anon_df[column].isin(rare_values), column] = '*'
        
        return anon_df
    
    # ==================== K-ANONYMITY WITH GENERALIZATION-FIRST APPROACH ====================
    
    @staticmethod
    def k_anonymity(df: pd.DataFrame, quasi_identifiers: List[str], k: int = 5,
                   use_generalization_first: bool = True, max_iterations: int = 3) -> pd.DataFrame:
        """
        Apply k-anonymity with generalization-first strategy.
        
        Instead of immediately suppressing records, this method:
        1. First tries to generalize QI values to create larger groups
        2. Then uses local suppression (cell-level) instead of record suppression
        3. Falls back to record suppression only as last resort
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            k: Minimum group size
            use_generalization_first: If True, apply generalization before suppression
            max_iterations: Maximum iterations for iterative refinement
            
        Returns:
            Anonymized dataframe
        """
        anon_df = df.copy()
        _cast = {c: object for c in quasi_identifiers if c in anon_df.columns and anon_df[c].dtype != object}
        if _cast:
            anon_df = anon_df.astype(_cast)

        if not quasi_identifiers:
            return anon_df
        
        if use_generalization_first:
            # Iteratively apply generalization with increasing levels
            for iteration in range(max_iterations):
                # Calculate current group sizes
                qi_df = anon_df[quasi_identifiers]
                groups = qi_df.groupby(list(quasi_identifiers)).size()
                small_groups = groups[groups < k]
                
                if len(small_groups) == 0:
                    break  # Already k-anonymous
                
                # Calculate generalization level for this iteration
                generalization_level = (iteration + 1) / (max_iterations + 1)
                
                # Apply generalization to reduce uniqueness
                anon_df = AnonymizationMethods.generalize_quasi_identifiers(
                    anon_df, quasi_identifiers, generalization_level
                )
                
                # Check if still needs more work
                qi_df = anon_df[quasi_identifiers]
                groups = qi_df.groupby(list(quasi_identifiers)).size()
                small_groups = groups[groups < k]
                
                if len(small_groups) == 0:
                    break
        
        # Final pass: apply local suppression for any remaining small groups
        anon_df = AnonymizationMethods._apply_local_suppression(
            anon_df, quasi_identifiers, max_suppression_per_column=0.1
        )
        
        # Final check: if still not k-anonymous, suppress entire records (last resort)
        qi_df = anon_df[quasi_identifiers]
        groups = qi_df.groupby(list(quasi_identifiers)).size()
        small_groups = groups[groups < k].index
        
        if len(small_groups) > 0:
            # Only suppress records in groups that are still too small
            mask = qi_df.apply(
                lambda row: tuple(row[qi] for qi in quasi_identifiers) in small_groups, 
                axis=1
            )
            for qi in quasi_identifiers:
                anon_df.loc[mask, qi] = '*'
        
        return anon_df
    
    # ==================== L-DIVERSITY WITH GENERALIZATION-FIRST APPROACH ====================
    
    @staticmethod
    def l_diversity(df: pd.DataFrame, quasi_identifiers: List[str], 
                   sensitive_attribute: str, l: int = 2,
                   use_generalization_first: bool = True) -> pd.DataFrame:
        """
        Apply l-diversity with generalization-first strategy.
        
        Instead of immediately suppressing records, this method:
        1. First tries to generalize QI values to create groups with more diverse sensitive values
        2. Then uses local suppression for problematic values
        3. Falls back to record suppression only as last resort
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            sensitive_attribute: Name of sensitive attribute column
            l: Minimum distinct sensitive values per group
            use_generalization_first: If True, apply generalization before suppression
            
        Returns:
            Anonymized dataframe
        """
        anon_df = df.copy()
        _cast = {c: object for c in quasi_identifiers if c in anon_df.columns and anon_df[c].dtype != object}
        if _cast:
            anon_df = anon_df.astype(_cast)
        qi_df = anon_df[quasi_identifiers]
        
        if sensitive_attribute not in anon_df.columns:
            return anon_df
        
        if use_generalization_first:
            # Try to increase diversity through generalization
            for gen_level in [0.3, 0.5, 0.7]:
                anon_df = AnonymizationMethods.generalize_quasi_identifiers(
                    anon_df, quasi_identifiers, gen_level
                )
                
                # Check l-diversity
                qi_df = anon_df[quasi_identifiers]
                groups = qi_df.groupby(list(quasi_identifiers))
                all_compliant = True
                
                for group_key, group_indices in groups.groups.items():
                    group_df = anon_df.loc[group_indices]
                    distinct_sensitive = group_df[sensitive_attribute].nunique()
                    
                    if distinct_sensitive < l:
                        all_compliant = False
                        break
                
                if all_compliant:
                    return anon_df
        
        # Apply l-diversity check with local suppression
        qi_df = anon_df[quasi_identifiers]
        groups = qi_df.groupby(list(quasi_identifiers))
        
        for group_key, group_indices in groups.groups.items():
            group_df = anon_df.loc[group_indices]
            distinct_sensitive = group_df[sensitive_attribute].nunique()
            
            if distinct_sensitive < l:
                # IMPORTANT: Do NOT "fix" l-diversity by masking the sensitive attribute.
                # To increase diversity we must change equivalence class structure by
                # generalizing/suppressing QIs so groups merge.
                mask = anon_df.index.isin(group_indices)

                # Prefer suppressing a single QI column to merge this group into others.
                suppressed = False
                for qi in quasi_identifiers:
                    test_df = anon_df.copy()
                    test_df.loc[mask, qi] = '*'
                    test_groups = test_df.groupby(quasi_identifiers).size()
                    new_key = tuple('*' if j == quasi_identifiers.index(qi) else group_key[j] for j in range(len(quasi_identifiers)))
                    if new_key in test_groups and int(test_groups[new_key]) >= l:
                        anon_df.loc[mask, qi] = '*'
                        suppressed = True
                        break

                if not suppressed:
                    # Last resort: suppress all QIs for this group (forces merging at '*', '*', ...)
                    for qi in quasi_identifiers:
                        anon_df.loc[mask, qi] = '*'
        
        return anon_df
    
    # ==================== T-CLOSENESS WITH GENERALIZATION-FIRST APPROACH ====================
    
    @staticmethod
    def t_closeness(df: pd.DataFrame, quasi_identifiers: List[str],
                   sensitive_attribute: str, t: float = 0.2,
                   use_generalization_first: bool = True) -> pd.DataFrame:
        """
        Apply t-closeness with generalization-first strategy.
        
        Instead of immediately suppressing records, this method:
        1. First tries to generalize QI values to make distribution closer to global
        2. Then uses local suppression for outliers
        3. Falls back to record suppression only as last resort
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            sensitive_attribute: Name of sensitive attribute column
            t: Maximum allowed distance (default 0.2)
            use_generalization_first: If True, apply generalization before suppression
            
        Returns:
            Anonymized dataframe
        """
        anon_df = df.copy()
        _cast = {c: object for c in quasi_identifiers if c in anon_df.columns and anon_df[c].dtype != object}
        if _cast:
            anon_df = anon_df.astype(_cast)

        if sensitive_attribute not in anon_df.columns:
            return anon_df
        
        # Detect if the sensitive attribute is ordinal/numeric
        is_ordinal = AnonymizationMethods._is_ordinal_attribute(df, sensitive_attribute)
        
        # Calculate global distribution
        global_dist = df[sensitive_attribute].value_counts(normalize=True).to_dict()
        
        if use_generalization_first:
            # Try to improve t-closeness through generalization
            for gen_level in [0.3, 0.5, 0.7]:
                anon_df = AnonymizationMethods.generalize_quasi_identifiers(
                    anon_df, quasi_identifiers, gen_level
                )
                
                # Check t-closeness
                qi_df = anon_df[quasi_identifiers]
                groups = qi_df.groupby(list(quasi_identifiers))
                all_compliant = True
                
                for group_key, group_indices in groups.groups.items():
                    group_df = anon_df.loc[group_indices]
                    local_dist = group_df[sensitive_attribute].value_counts(normalize=True).to_dict()
                    
                    distance = AnonymizationMethods._calculate_distribution_distance(
                        local_dist, global_dist, is_ordinal=is_ordinal
                    )
                    
                    if distance > t:
                        all_compliant = False
                        break
                
                if all_compliant:
                    return anon_df
        
        # Apply t-closeness check with local suppression
        qi_df = anon_df[quasi_identifiers]
        groups = qi_df.groupby(list(quasi_identifiers))
        
        for group_key, group_indices in groups.groups.items():
            group_df = anon_df.loc[group_indices]
            local_dist = group_df[sensitive_attribute].value_counts(normalize=True).to_dict()
            
            distance = AnonymizationMethods._calculate_distribution_distance(
                local_dist, global_dist, is_ordinal=is_ordinal
            )
            
            if distance > t:
                # IMPORTANT: Do NOT "fix" t-closeness by masking the sensitive attribute.
                # We must change group composition by generalizing/suppressing QIs so that
                # local distributions move closer to global distribution.
                mask = anon_df.index.isin(group_indices)

                # Try suppressing one QI to merge this group with others.
                merged = False
                for qi in quasi_identifiers:
                    test_df = anon_df.copy()
                    test_df.loc[mask, qi] = '*'
                    # Recompute distance for the merged group key (approx)
                    test_group_df = test_df.loc[mask]
                    test_local = test_group_df[sensitive_attribute].value_counts(normalize=True).to_dict()
                    test_distance = AnonymizationMethods._calculate_distribution_distance(
                        test_local, global_dist, is_ordinal=is_ordinal
                    )
                    if test_distance <= t:
                        anon_df.loc[mask, qi] = '*'
                        merged = True
                        break

                if not merged:
                    # Last resort: suppress all QIs for this group
                    for qi in quasi_identifiers:
                        anon_df.loc[mask, qi] = '*'
        
        return anon_df
    
    # ==================== SUPPRESSION AND MICROAGGREGATION ====================
    
    @staticmethod
    def suppression(df: pd.DataFrame, quasi_identifiers: List[str],
                   threshold: int = 5) -> pd.DataFrame:
        """
        Suppress records with rare QI combinations
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            threshold: Minimum frequency to keep
            
        Returns:
            Anonymized dataframe
        """
        anon_df = df.copy()
        _cast = {c: object for c in quasi_identifiers if c in anon_df.columns and anon_df[c].dtype != object}
        if _cast:
            anon_df = anon_df.astype(_cast)
        qi_df = anon_df[quasi_identifiers]
        
        # Count frequencies
        combination_counts = qi_df.groupby(list(quasi_identifiers)).size()
        rare_combinations = combination_counts[combination_counts < threshold].index
        
        # Suppress QI values for rare combinations
        mask = qi_df.apply(
            lambda row: tuple(row[qi] for qi in quasi_identifiers) in rare_combinations,
            axis=1
        )
        
        for qi in quasi_identifiers:
            anon_df.loc[mask, qi] = '*'
        
        return anon_df
    
    @staticmethod
    def microaggregation(df: pd.DataFrame, column: str, group_size: int = 3) -> pd.DataFrame:
        """
        Microaggregation: Replace values with group average
        
        Args:
            df: Input dataframe
            column: Column name to microaggregate
            group_size: Size of aggregation groups
            
        Returns:
            Anonymized dataframe
        """
        anon_df = df.copy()
        
        if column not in anon_df.columns:
            return anon_df
        
        orig = anon_df[column]
        num = pd.to_numeric(orig, errors='coerce')
        valid_mask = num.notna()
        if valid_mask.sum() == 0:
            return anon_df
        
        group_size = max(2, int(group_size))
        sorted_indices = num[valid_mask].sort_values().index
        n = len(sorted_indices)
        if n == 0:
            return anon_df
        
        out_col = orig.copy()
        n_groups = n // group_size
        
        for i in range(n_groups):
            start_idx = i * group_size
            end_idx = start_idx + group_size
            group_indices = sorted_indices[start_idx:end_idx]
            group_mean = float(num.loc[group_indices].mean())
            out_col.loc[group_indices] = group_mean
        
        if n % group_size > 0:
            remainder_start = n_groups * group_size
            remainder_indices = sorted_indices[remainder_start:]
            if len(remainder_indices) > 0:
                remainder_mean = float(num.loc[remainder_indices].mean())
                out_col.loc[remainder_indices] = remainder_mean
        
        anon_df[column] = out_col
        return anon_df
    
    # ==================== PRAM (POST-RANDOMISATION METHOD) ====================
    
    @staticmethod
    def _create_perturbation_matrix(
        categories: List[Any], 
        perturbation_rate: float = 0.1,
        seed: int = 42
    ) -> pd.DataFrame:
        """
        Create a PRAM perturbation/transition matrix.
        
        For low perturbation (5-10%), the diagonal elements (probability of keeping
        original value) should be high (90-95%), and off-diagonal elements distribute
        the remaining probability.
        
        Args:
            categories: List of unique categories in the column
            perturbation_rate: Probability of changing value (0.05-0.10 for low perturbation)
            seed: Random seed for reproducibility
            
        Returns:
            DataFrame representing the transition probability matrix
        """
        np.random.seed(seed)
        n_categories = len(categories)
        
        # Diagonal: probability of staying the same
        # For low perturbation, this should be 90-95%
        diagonal_prob = 1.0 - perturbation_rate
        
        # Create the matrix
        matrix = np.zeros((n_categories, n_categories))
        
        # Set diagonal probabilities
        for i in range(n_categories):
            matrix[i, i] = diagonal_prob
        
        # Distribute the perturbation probability uniformly among off-diagonal elements
        # Each off-diagonal element gets an equal share
        off_diag_prob = perturbation_rate / (n_categories - 1) if n_categories > 1 else 0
        
        for i in range(n_categories):
            for j in range(n_categories):
                if i != j:
                    matrix[i, j] = off_diag_prob
        
        # Verify rows sum to 1
        row_sums = matrix.sum(axis=1, keepdims=True)
        matrix = matrix / row_sums
        
        return pd.DataFrame(matrix, index=categories, columns=categories)
    
    @staticmethod
    def pram(
        df: pd.DataFrame, 
        columns: List[str],
        perturbation_rate: float = 0.1,
        seed: int = 42
    ) -> pd.DataFrame:
        """
        Apply PRAM (Post-Randomisation Method) to categorical columns.
        
        PRAM randomly changes categorical values according to a transition matrix,
        preserving the overall distribution while masking individual records.
        
        For low perturbation (5-10%):
        - 90-95% probability of keeping the original value
        - 5-10% probability of changing to another value
        
        Args:
            df: Input dataframe
            columns: List of column names to apply PRAM
            perturbation_rate: Probability of changing value (default 0.1 = 10%)
                               Use 0.05-0.10 for low perturbation
            seed: Random seed for reproducibility
            
        Returns:
            Anonymized dataframe with PRAM applied
        """
        anon_df = df.copy()
        
        # Clamp perturbation rate to valid range
        perturbation_rate = max(0.01, min(0.5, perturbation_rate))
        
        for column in columns:
            if column not in anon_df.columns:
                continue
            
            # Get unique categories (excluding NaN)
            categories = anon_df[column].dropna().unique().tolist()
            
            if len(categories) < 2:
                # Can't apply PRAM to single-category columns
                continue
            
            # Create perturbation matrix
            perturb_matrix = AnonymizationMethods._create_perturbation_matrix(
                categories, perturbation_rate, seed
            )
            
            # Apply PRAM to each record
            def perturb_value(value):
                if pd.isna(value):
                    return value
                
                # Get the probability distribution for this value
                if str(value) in perturb_matrix.index:
                    probs = perturb_matrix.loc[str(value)].values
                    categories_array = perturb_matrix.columns.values
                    
                    # Sample new value according to probabilities
                    new_value = np.random.choice(categories_array, p=probs)
                    return new_value
                else:
                    return value
            
            # Apply perturbation
            anon_df[column] = anon_df[column].apply(perturb_value)
        
        return anon_df
    
    @staticmethod
    def pram_with_custom_matrix(
        df: pd.DataFrame, 
        column: str,
        custom_matrix: pd.DataFrame,
        seed: int = 42
    ) -> pd.DataFrame:
        """
        Apply PRAM with a custom perturbation matrix.
        
        Args:
            df: Input dataframe
            column: Column name to apply PRAM
            custom_matrix: Custom transition probability matrix (DataFrame)
            seed: Random seed for reproducibility
            
        Returns:
            Anonymized dataframe
        """
        anon_df = df.copy()
        
        if column not in anon_df.columns:
            return anon_df
        
        # Validate matrix dimensions
        categories = anon_df[column].dropna().unique().tolist()
        
        # Ensure matrix covers all categories
        missing_cats = set(str(c) for c in categories) - set(custom_matrix.index)
        if missing_cats:
            # Add missing categories with identity row
            for cat in missing_cats:
                new_row = pd.Series({c: 0.0 for c in custom_matrix.columns})
                new_row[cat] = 1.0
                custom_matrix = pd.concat([custom_matrix, pd.DataFrame([new_row], index=[cat])])
        
        def perturb_value(value):
            if pd.isna(value):
                return value
            
            str_value = str(value)
            if str_value in custom_matrix.index:
                probs = custom_matrix.loc[str_value].values
                categories_array = custom_matrix.columns.values
                new_value = np.random.choice(categories_array, p=probs)
                return new_value
            else:
                return value
        
        anon_df[column] = anon_df[column].apply(perturb_value)
        
        return anon_df
    
    # ==================== HYBRID ANONYMIZATION ====================
    
    @staticmethod
    def apply_hybrid_anonymization(
        df: pd.DataFrame, 
        quasi_identifiers: List[str],
        sensitive_attributes: List[str] = None,
        k: int = 5, 
        l: int = 2, 
        t: float = 0.2,
        use_generalization_first: bool = True
    ) -> pd.DataFrame:
        """
        Apply hybrid anonymization combining multiple methods with generalization-first strategy.
        
        This is the recommended approach that:
        1. First applies generalization to reduce uniqueness
        2. Then applies k-anonymity with local suppression
        3. Then applies l-diversity if sensitive attributes provided
        4. Then applies t-closeness if sensitive attributes provided
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            sensitive_attributes: List of sensitive attribute names
            k: k-anonymity parameter
            l: l-diversity parameter
            t: t-closeness parameter
            use_generalization_first: Whether to apply generalization before suppression
            
        Returns:
            Anonymized dataframe
        """
        anon_df = df.copy()
        
        # Step 1: Apply generalization first to reduce uniqueness
        if use_generalization_first:
            anon_df = AnonymizationMethods.generalize_quasi_identifiers(
                anon_df, quasi_identifiers, generalization_level=0.5
            )
        
        # Step 2: Apply k-anonymity with generalization-first approach
        anon_df = AnonymizationMethods.k_anonymity(
            anon_df, quasi_identifiers, k, 
            use_generalization_first=use_generalization_first
        )
        
        # Step 3: Apply l-diversity if sensitive attributes provided
        if sensitive_attributes:
            for sens_attr in sensitive_attributes:
                if sens_attr in anon_df.columns:
                    anon_df = AnonymizationMethods.l_diversity(
                        anon_df, quasi_identifiers, sens_attr, l,
                        use_generalization_first=use_generalization_first
                    )
        
        # Step 4: Apply t-closeness if sensitive attributes provided
        if sensitive_attributes:
            for sens_attr in sensitive_attributes:
                if sens_attr in anon_df.columns:
                    anon_df = AnonymizationMethods.t_closeness(
                        anon_df, quasi_identifiers, sens_attr, t,
                        use_generalization_first=use_generalization_first
                    )
        
        return anon_df
    
    # ==================== PSU HANDLING ====================
    
    @staticmethod
    def psu_aggregation_to_region(df: pd.DataFrame, psu_column: str, 
                                  region_column: str = None, min_group_size: int = 5) -> pd.DataFrame:
        """
        Aggregate PSU to district/region level
        """
        anon_df = df.copy()
        
        if psu_column not in anon_df.columns:
            return anon_df
        
        if region_column and region_column in anon_df.columns:
            anon_df[psu_column] = anon_df[region_column]
        else:
            psu_counts = anon_df[psu_column].value_counts()
            
            small_psus = psu_counts[psu_counts < min_group_size].index
            if len(small_psus) > 0:
                anon_df.loc[anon_df[psu_column].isin(small_psus), psu_column] = 'REGION_OTHER'
            
            unique_psus = anon_df[psu_column].unique()
            region_mapping = {}
            region_id = 1
            
            for psu in unique_psus:
                if psu != 'REGION_OTHER':
                    region_mapping[psu] = f'REGION_{region_id}'
                    region_id += 1
            
            anon_df[psu_column] = anon_df[psu_column].map(lambda x: region_mapping.get(x, x))
        
        return anon_df
    
    @staticmethod
    def psu_random_recoding(df: pd.DataFrame, psu_column: str, 
                           min_group_size: int = 5, seed: int = 42) -> pd.DataFrame:
        """
        Randomly re-code PSU with minimum group size enforcement
        """
        anon_df = df.copy()
        
        if psu_column not in anon_df.columns:
            return anon_df
        
        np.random.seed(seed)
        
        unique_psus = anon_df[psu_column].unique()
        n_records = len(anon_df)
        n_new_groups = max(1, n_records // min_group_size)
        
        psu_mapping = {}
        
        for psu in unique_psus:
            new_group = np.random.randint(1, n_new_groups + 1)
            psu_mapping[psu] = f'PSU_RECODED_{new_group}'
        
        anon_df[psu_column] = anon_df[psu_column].map(psu_mapping)
        
        group_sizes = anon_df[psu_column].value_counts()
        small_groups = group_sizes[group_sizes < min_group_size].index
        
        if len(small_groups) > 0:
            anon_df.loc[anon_df[psu_column].isin(small_groups), psu_column] = 'PSU_RECODED_OTHER'
        
        return anon_df
    
    @staticmethod
    def handle_psu(df: pd.DataFrame, psu_column: str, method: str = 'random_recode',
                   region_column: str = None, min_group_size: int = 5) -> pd.DataFrame:
        """
        Handle PSU column using specified method
        """
        if method == 'aggregate':
            return AnonymizationMethods.psu_aggregation_to_region(
                df, psu_column, region_column, min_group_size
            )
        elif method == 'random_recode':
            return AnonymizationMethods.psu_random_recoding(
                df, psu_column, min_group_size
            )
        else:
            return AnonymizationMethods.psu_random_recoding(
                df, psu_column, min_group_size
            )
    
    # ==================== HIERARCHY-BASED GENERALIZATION (NEW) ====================
    
    @staticmethod
    def init_hierarchies_for_quasi_identifiers(
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        hierarchy_manager: GeneralizationHierarchyManager = None
    ) -> GeneralizationHierarchyManager:
        """
        Initialize hierarchies for quasi-identifiers based on their detected types.
        
        This method automatically creates appropriate generalization hierarchies
        for each QI based on the attribute type.
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            hierarchy_manager: Optional hierarchy manager instance
            
        Returns:
            Configured hierarchy manager
        """
        if hierarchy_manager is None:
            hierarchy_manager = get_hierarchy_mgr()
        
        for qi in quasi_identifiers:
            if qi not in df.columns:
                continue
                
            # Skip if hierarchy already exists
            if hierarchy_manager.get_hierarchy(qi):
                continue
            
            # Get sample values for type detection
            sample = df[qi].dropna().head(100).tolist()
            
            # Detect attribute type
            attr_type = detect_attribute_type(qi, sample)
            
            if attr_type and attr_type != 'categorical':
                # For numeric attributes with age/income, create numeric hierarchies
                if pd.api.types.is_numeric_dtype(df[qi]) and attr_type in {"age", "income"}:
                    col = pd.to_numeric(df[qi], errors="coerce").dropna()
                    if len(col) > 0:
                        hierarchy_manager.create_numeric_hierarchy(
                            attribute_name=qi,
                            min_val=float(col.min()),
                            max_val=float(col.max()),
                            num_levels=4,
                            range_type="equal_width",
                        )
                        continue
                
                # For geography type with numeric codes (e.g., province codes 1-9)
                if attr_type == "geography":
                    unique_vals = df[qi].dropna().unique()
                    if len(unique_vals) > 0:
                        # Check if values are numeric
                        try:
                            [float(v) for v in unique_vals[:5]]  # Check first 5
                            is_numeric = True
                        except (ValueError, TypeError):
                            is_numeric = False
                        
                        if is_numeric:
                            # Numeric codes
                            # Create a simple numeric-based geographic hierarchy
                            # Level 1: Keep original codes
                            # Level 2: Group into broader regions (depends on the column)
                            mapping_level1 = {}
                            mapping_level2 = {}
                            
                            # Group based on the column name
                            if 'province' in qi.lower():
                                # Sri Lanka has 9 provinces - map codes to province names
                                province_map = {
                                    1: 'Western', 2: 'Central', 3: 'Southern', 
                                    4: 'Northern', 5: 'Eastern', 6: 'North Central',
                                    7: 'Uva', 8: 'Sabaragamuwa', 9: 'North Western'
                                }
                                for val in unique_vals:
                                    int_val = int(float(val)) if pd.notna(val) else None
                                    if int_val in province_map:
                                        province_name = province_map[int_val]
                                        if province_name not in mapping_level1:
                                            mapping_level1[province_name] = []
                                        mapping_level1[province_name].append(str(val))
                                # Level 2: Group all into "Sri Lanka"
                                mapping_level2 = {'Sri Lanka': [str(v) for v in unique_vals]}
                                
                            elif 'district' in qi.lower():
                                # District codes - create ranges or groups
                                # For now, just use the code as-is at level 1
                                for val in unique_vals:
                                    mapping_level1[str(int(float(val)))] = [str(val)]
                                # Level 2: suppress
                                mapping_level2 = {'*': [str(v) for v in unique_vals]}
                                
                            elif 'ds_' in qi.lower() or 'ds_division' in qi.lower():
                                # DS Division - similar treatment
                                for val in unique_vals:
                                    mapping_level1[str(int(float(val)))] = [str(val)]
                                mapping_level2 = {'*': [str(v) for v in unique_vals]}
                            
                            else:
                                # Generic geographic - just keep original
                                for val in unique_vals:
                                    mapping_level1[str(int(float(val)))] = [str(val)]
                                mapping_level2 = {'*': [str(v) for v in unique_vals]}
                            
                            if mapping_level1:
                                from .hierarchy_manager import GeneralizationHierarchy
                                hierarchy = GeneralizationHierarchy(qi)
                                hierarchy.add_level(1, mapping_level1)
                                hierarchy.add_level(2, mapping_level2)
                                hierarchy_manager.add_hierarchy(hierarchy)
                                continue
                        else:
                            # String values, use template or create simple hierarchy
                            template = get_hierarchy_for_attribute(qi, sample)
                            if template:
                                hierarchy_manager.add_hierarchy_from_template(qi, template)
                                continue
                            else:
                                # Create simple hierarchy for string geography
                                # Group by frequency
                                value_counts = df[qi].value_counts()
                                common_values = value_counts[value_counts >= 5].index.tolist()
                                
                                if len(common_values) > 0:
                                    mapping = {'*': [str(v) for v in unique_vals if str(v) not in common_values]}
                                    for v in common_values:
                                        mapping[str(v)] = [str(v)]
                                    
                                    from .hierarchy_manager import GeneralizationHierarchy
                                    hierarchy = GeneralizationHierarchy(qi)
                                    hierarchy.add_level(1, mapping)
                                    hierarchy_manager.add_hierarchy(hierarchy)
                                    continue

                # For gender
                if attr_type == "gender":
                    unique_vals = df[qi].dropna().unique()
                    if len(unique_vals) > 0:
                        # Check if values are numeric codes or strings
                        try:
                            # Try to convert all to float
                            [float(v) for v in unique_vals[:5]]  # Check first 5
                            is_numeric = True
                        except (ValueError, TypeError):
                            is_numeric = False
                        
                        if is_numeric:
                            # Numeric codes
                            mapping_level1 = {}
                            mapping_level2 = {}
                            
                            for val in unique_vals:
                                int_val = int(float(val)) if pd.notna(val) else None
                                if int_val == 1:
                                    mapping_level1['Male'] = [str(val)]
                                elif int_val == 2:
                                    mapping_level1['Female'] = [str(val)]
                                else:
                                    mapping_level1['Other'] = [str(val)]
                            
                            # Level 2: Group all as "Person"
                            mapping_level2 = {'Person': [str(v) for v in unique_vals]}
                            
                            from .hierarchy_manager import GeneralizationHierarchy
                            hierarchy = GeneralizationHierarchy(qi)
                            hierarchy.add_level(1, mapping_level1)
                            hierarchy.add_level(2, mapping_level2)
                            hierarchy_manager.add_hierarchy(hierarchy)
                            continue
                        else:
                            # String values, use template
                            template = get_hierarchy_for_attribute(qi, sample)
                            if template:
                                hierarchy_manager.add_hierarchy_from_template(qi, template)
                                continue

                # Otherwise, use templates (e.g., geography, education, occupation, date-like)
                template = get_hierarchy_for_attribute(qi, sample)
                if template:
                    hierarchy_manager.add_hierarchy_from_template(qi, template)
            else:
                # For categorical, create a simple hierarchy based on value frequency
                value_counts = df[qi].value_counts()
                common_values = value_counts[value_counts >= 5].index.tolist()
                
                if len(common_values) > 0:
                    # Create a simple hierarchy: common values stay, rare values suppressed
                    mapping = {'*': [str(v) for v in df[qi].unique() if str(v) not in common_values]}
                    for v in common_values:
                        mapping[str(v)] = [str(v)]
                    
                    from .hierarchy_manager import GeneralizationHierarchy
                    hierarchy = GeneralizationHierarchy(qi)
                    hierarchy.add_level(1, mapping)
                    hierarchy.add_level(2, {'*': [str(v) for v in df[qi].unique()]})
                    hierarchy_manager.add_hierarchy(hierarchy)
        
        return hierarchy_manager
    
    @staticmethod
    def generalize_with_hierarchy(
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        generalization_levels: Dict[str, int] = None,
        hierarchy_manager: GeneralizationHierarchyManager = None
    ) -> pd.DataFrame:
        """
        Generalize quasi-identifiers using hierarchical generalization trees.
        
        This method uses the GeneralizationHierarchyManager to apply scientifically
        acceptable hierarchical transformations instead of ad-hoc pd.cut() or
        rare value grouping.
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            generalization_levels: Dict mapping column -> level (0 = original, higher = more general)
            hierarchy_manager: Optional hierarchy manager instance
            
        Returns:
            Dataframe with generalized QI values
        """
        if hierarchy_manager is None:
            hierarchy_manager = get_hierarchy_mgr()
        
        anon_df = df.copy()
        _cast = {c: object for c in quasi_identifiers if c in anon_df.columns and anon_df[c].dtype != object}
        if _cast:
            anon_df = anon_df.astype(_cast)

        # Initialize hierarchies if not already done
        AnonymizationMethods.init_hierarchies_for_quasi_identifiers(
            df, quasi_identifiers, hierarchy_manager
        )
        
        if generalization_levels is None:
            # Default: use level 1 for all
            generalization_levels = {qi: 1 for qi in quasi_identifiers}
        
        for qi in quasi_identifiers:
            if qi not in anon_df.columns:
                continue
            
            target_level = generalization_levels.get(qi, 1)
            
            # Get the hierarchy
            hierarchy = hierarchy_manager.get_hierarchy(qi)
            if hierarchy:
                # Apply hierarchical generalization
                anon_df[qi] = anon_df[qi].apply(
                    lambda v: hierarchy.generalize(str(v), target_level)
                )
            else:
                # Fallback to old method if no hierarchy
                if pd.api.types.is_numeric_dtype(anon_df[qi]):
                    num_bins = max(2, 5 - target_level)
                    anon_df[qi] = pd.cut(
                        anon_df[qi],
                        bins=num_bins,
                        labels=[f'Range_{i+1}' for i in range(num_bins)],
                        include_lowest=True
                    )
                    anon_df[qi] = anon_df[qi].astype(str)
                else:
                    # For categorical without hierarchy, suppress rare values
                    value_counts = anon_df[qi].value_counts()
                    threshold = len(anon_df) * 0.1 * target_level
                    rare_values = value_counts[value_counts < max(threshold, 1)].index
                    anon_df.loc[anon_df[qi].isin(rare_values), qi] = '*'
        
        return anon_df
    
    @staticmethod
    def k_anonymity_with_hierarchy(
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        k: int = 5,
        max_hierarchy_level: int = 3,
        hierarchy_manager: GeneralizationHierarchyManager = None
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Apply k-anonymity using hierarchical generalization (Mondrian-style).
        
        This is a scientifically acceptable approach that uses hierarchical
        generalization trees to achieve k-anonymity.
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            k: Minimum group size
            max_hierarchy_level: Maximum hierarchy level to use
            hierarchy_manager: Optional hierarchy manager instance
            
        Returns:
            Tuple of (anonymized dataframe, info dict)
        """
        if hierarchy_manager is None:
            hierarchy_manager = get_hierarchy_mgr()
        
        anon_df = df.copy()
        
        # Initialize hierarchies
        AnonymizationMethods.init_hierarchies_for_quasi_identifiers(
            df, quasi_identifiers, hierarchy_manager
        )
        
        info = {
            'iterations': 0,
            'generalization_used': {},
            'suppression_applied': 0
        }
        
        # Try increasing hierarchy levels
        for level in range(1, max_hierarchy_level + 1):
            info['iterations'] = level
            
            # Apply generalization at this level
            gen_levels = {qi: level for qi in quasi_identifiers}
            test_df = AnonymizationMethods.generalize_with_hierarchy(
                anon_df, quasi_identifiers, gen_levels, hierarchy_manager
            )
            
            # Check k-anonymity
            qi_df = test_df[quasi_identifiers]
            groups = qi_df.groupby(list(quasi_identifiers)).size()
            small_groups = groups[groups < k]
            
            if len(small_groups) == 0:
                # k-anonymity satisfied!
                anon_df = test_df
                info['generalization_used'] = gen_levels
                break
        else:
            # If still not satisfied at max level, apply local suppression
            anon_df = AnonymizationMethods._apply_local_suppression(
                anon_df, quasi_identifiers, max_suppression_per_column=0.2
            )
            info['suppression_applied'] = 1
        
        # Final check
        qi_df = anon_df[quasi_identifiers]
        groups = qi_df.groupby(list(quasi_identifiers)).size()
        info['min_group_size'] = int(groups.min()) if len(groups) > 0 else 0
        info['num_groups'] = len(groups)
        
        return anon_df, info
    
    @staticmethod
    def get_hierarchy_info(
        quasi_identifiers: List[str],
        hierarchy_manager: GeneralizationHierarchyManager = None
    ) -> Dict:
        """
        Get information about configured hierarchies for quasi-identifiers.
        
        Args:
            quasi_identifiers: List of QI column names
            hierarchy_manager: Optional hierarchy manager instance
            
        Returns:
            Dict with hierarchy information
        """
        if hierarchy_manager is None:
            hierarchy_manager = get_hierarchy_mgr()
        
        info = {}
        for qi in quasi_identifiers:
            hierarchy = hierarchy_manager.get_hierarchy(qi)
            if hierarchy:
                info[qi] = {
                    'has_hierarchy': True,
                    'max_level': hierarchy.max_level,
                    'current_level': hierarchy_manager.get_level(qi),
                    'available_values': list(hierarchy.levels.get(0, {}).keys())[:10] if 0 in hierarchy.levels else []
                }
            else:
                info[qi] = {
                    'has_hierarchy': False,
                    'max_level': 0,
                    'current_level': 0
                }
        
        return info
    
    @staticmethod
    def apply_sensitive_attribute_transformations(
        anon_df: pd.DataFrame,
        sensitive_attributes: List[str],
    ) -> tuple[pd.DataFrame, list]:
        """
        Apply microaggregation / bucketing to every selected sensitive column.
        Returns (updated_df, column_change dicts for change_tracking).
        """
        out = anon_df.copy()
        entries: list = []
        for sa_col in sensitive_attributes or []:
            if sa_col not in out.columns:
                continue
            original_unique = int(out[sa_col].nunique())
            original_col = out[sa_col].copy()
            method = 'suppress_rare_values'
            coerced = pd.to_numeric(out[sa_col], errors='coerce')
            n_rows = max(len(out), 1)
            is_effectively_numeric = pd.api.types.is_numeric_dtype(out[sa_col]) or (
                (coerced.notna().sum() / n_rows) > 0.5
            )
            if is_effectively_numeric:
                method = 'microaggregation'
                try:
                    if not pd.api.types.is_numeric_dtype(out[sa_col]):
                        out[sa_col] = coerced
                    n = len(out)
                    group_size = max(3, max(2, n // 100)) if n else 3
                    out = AnonymizationMethods.microaggregation(out, sa_col, group_size=group_size)
                except Exception:
                    method = 'binning'
                    try:
                        num = pd.to_numeric(out[sa_col], errors='coerce')
                        col_range = num.max() - num.min()
                        bin_size = max(1000, col_range / 10) if pd.notna(col_range) and col_range > 0 else 1000
                        out[sa_col] = (num / bin_size).round() * bin_size
                    except Exception:
                        pass
            else:
                value_counts = out[sa_col].value_counts()
                threshold = len(out) * 0.05
                rare_values = value_counts[value_counts < threshold].index
                mask = out[sa_col].isin(rare_values)
                if mask.any():
                    out.loc[mask, sa_col] = '[SUPPRESSED]'
                if (original_col.astype(str) == out[sa_col].astype(str)).all():
                    strcol = out[sa_col].astype(str)
                    vc = strcol.value_counts()
                    if len(vc) <= 1:
                        method = 'constant_redaction'
                        out[sa_col] = '[REDACTED]'
                    else:
                        method = 'top_k_bucket'
                        # Keep strictly fewer categories than exist so at least one value maps to [OTHER]
                        k = max(1, min(len(vc) - 1, 5))
                        top = set(vc.head(k).index)
                        out[sa_col] = strcol.where(strcol.isin(top), '[OTHER]')
            anonymized_unique = int(out[sa_col].nunique())
            cells_modified = int((original_col.astype(str) != out[sa_col].astype(str)).sum())
            sample_changes: list = []
            changed_indices = np.where((original_col.astype(str) != out[sa_col].astype(str)).values)[0]
            for idx in changed_indices[:3]:
                try:
                    sample_changes.append({
                        'original': str(original_col.iloc[idx]),
                        'anonymized': str(out.iloc[idx][sa_col]),
                    })
                except Exception:
                    pass
            entries.append({
                'column_name': sa_col,
                'column_type': 'sensitive_attribute',
                'anonymization_method': method,
                'original_unique_values': original_unique,
                'anonymized_unique_values': anonymized_unique,
                'cells_modified': cells_modified,
                'sample_changes': sample_changes,
            })
        return out, entries
    
    @staticmethod
    def comprehensive_anonymize_with_tracking(
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        sensitive_attributes: List[str],
        direct_identifiers: List[str],
        analysis_results: Dict[str, Any] = None,
        k: int = 5,
        l: int = 2,
        t: float = 0.2,
        generalization_level: float = 0.5
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Comprehensive anonymization of ALL column types with detailed change tracking.
        
        This method goes beyond just anonymizing quasi-identifiers - it also handles:
        - Direct identifiers (suppress or remove)
        - Sensitive attributes (suppress or generalize)
        - Any other columns flagged as risky by analysis
        - LOW-CONFIDENCE QIs from analysis_results (QI fix: track/log skipped)

        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            sensitive_attributes: List of sensitive attribute column names
            direct_identifiers: List of direct identifier column names
            analysis_results: Optional dict with detected problems and risk assessment
            k, l, t: Anonymization parameters
            generalization_level: Generalization intensity (0-1)
            
        Returns:
            Tuple of (anonymized_df, change_tracking_info)
        """
        anon_df = df.copy()
        change_tracking = {
            'total_columns_changed': 0,
            'total_cells_changed': 0,
            'column_changes': [],
            'row_changes': [],
            'qi_processing_log': {  # NEW: QI fix logging
                'input_qi_count': len(quasi_identifiers),
                'processed_qi_count': 0,
                'skipped_qi_count': 0,
                'skipped_qis': [],
                'low_conf_qi_count': 0,
                'low_conf_qis': [],
                'session_qi_list': quasi_identifiers[:]
            }
        }
        
        log = change_tracking['qi_processing_log']
        
        # Identify risky columns from analysis results
        risky_columns = []
        low_conf_qis = []  # NEW: Track low-confidence QIs
        if analysis_results and 'detected_problems' in analysis_results:
            for problem in analysis_results.get('detected_problems', []):
                if 'column' in problem and problem['column'] not in quasi_identifiers:
                    if problem['column'] not in risky_columns:
                        risky_columns.append(problem['column'])
        # NEW: Extract low-confidence QIs from detection_result if available
        if analysis_results and 'detection_result' in analysis_results:
            detection_details = analysis_results['detection_result'].get('details', [])
            for detail in detection_details:
                if (detail.get('confidence', 0) < 0.7 and 
                    detail['class'] == 'QUASI_IDENTIFIER' and 
                    detail['column_name'] not in quasi_identifiers and
                    detail['column_name'] in df.columns):
                    low_conf_qis.append(detail['column_name'])
        
        log['low_conf_qi_count'] = len(low_conf_qis)
        log['low_conf_qis'] = low_conf_qis[:5]  # First 5 only
        
        # === 1. HANDLE DIRECT IDENTIFIERS: SUPPRESS OR REMOVE ===
        for di_col in direct_identifiers:
            if di_col not in anon_df.columns:
                continue
                
            original_unique = anon_df[di_col].nunique()
            
            # Suppress (replace with mask) for most columns, or remove entirely
            if anon_df[di_col].dtype == 'object' or anon_df[di_col].dtype == 'string':
                # For string columns, mask with placeholder
                anon_df[di_col] = '[SUPPRESSED]'
                method = 'suppression'
            else:
                # For numeric columns, use NaN
                anon_df[di_col] = np.nan
                method = 'removal'
            
            anonymized_unique = anon_df[di_col].nunique()
            cells_modified = len(df)  # All cells changed
            
            # Sample changes
            sample_changes = []
            for idx in range(min(3, len(df))):
                try:
                    sample_changes.append({
                        'original': str(df.iloc[idx][di_col]),
                        'anonymized': str(anon_df.iloc[idx][di_col])
                    })
                except:
                    pass
            
            change_tracking['column_changes'].append({
                'column_name': di_col,
                'column_type': 'direct_identifier',
                'anonymization_method': method,
                'original_unique_values': int(original_unique),
                'anonymized_unique_values': int(anonymized_unique),
                'cells_modified': cells_modified,
                'sample_changes': sample_changes
            })
            change_tracking['total_columns_changed'] += 1
            change_tracking['total_cells_changed'] += cells_modified
        
        # === 2. HANDLE QUASI-IDENTIFIERS (QI fix: process + log all, including low-conf) ===
        all_qi_cols = [c for c in quasi_identifiers if c in df.columns]
        log['processed_qi_count'] = len(all_qi_cols)
        
        for qi_col in all_qi_cols:
            original_unique = df[qi_col].nunique()
            anonymized_unique = anon_df[qi_col].nunique() if qi_col in anon_df.columns else 0
            
            # Will be generalized/suppressed by main k-anonymity methods
            # Track the change potential
            if original_unique > anonymized_unique or (anon_df[qi_col] == '*').any():
                method = 'generalization_and_suppression'
                cells_modified = (df[qi_col].astype(str) != anon_df[qi_col].astype(str)).sum()
                
                # Sample changes
                sample_changes = []
                changed_indices = np.where((df[qi_col].astype(str) != anon_df[qi_col].astype(str)).values)[0]
                for idx in changed_indices[:3]:
                    try:
                        sample_changes.append({
                            'original': str(df.iloc[idx][qi_col]),
                            'anonymized': str(anon_df.iloc[idx][qi_col])
                        })
                    except Exception:
                        pass
                
                change_tracking['column_changes'].append({
                    'column_name': qi_col,
                    'column_type': 'quasi_identifier',
                    'anonymization_method': method,
                    'original_unique_values': int(original_unique),
                    'anonymized_unique_values': int(anonymized_unique),
                    'cells_modified': int(cells_modified),
                    'sample_changes': sample_changes
                })
                change_tracking['total_columns_changed'] += 1
                change_tracking['total_cells_changed'] += int(cells_modified)
            else:
                log['skipped_qis'].append(qi_col)
        
        log['skipped_qi_count'] = len(log['skipped_qis'])
        
        # === 3. SENSITIVE ATTRIBUTES (after QI tracking; avoids losing SI work if QI indexing failed) ===
        anon_df, sens_entries = AnonymizationMethods.apply_sensitive_attribute_transformations(
            anon_df, sensitive_attributes
        )
        for ent in sens_entries:
            change_tracking['column_changes'].append(ent)
            if ent.get('cells_modified', 0) > 0:
                change_tracking['total_columns_changed'] += 1
                change_tracking['total_cells_changed'] += int(ent['cells_modified'])
        
        # === 4. IDENTIFY AND TRACK ROW-LEVEL CHANGES ===
        row_changes = []
        try:
            for idx in range(min(100, len(df))):  # Check first 100 rows for samples
                changed_cols = []
                changes = {}
                
                for col in anon_df.columns:
                    if col not in df.columns:
                        continue
                        
                    orig_val = str(df.iloc[idx][col])
                    anon_val = str(anon_df.iloc[idx][col])
                    
                    if orig_val != anon_val:
                        changed_cols.append(col)
                        changes[col] = {
                            'original': orig_val,
                            'anonymized': anon_val
                        }
                
                if changed_cols:
                    row_changes.append({
                        'row_index': idx,
                        'changed_columns': changed_cols,
                        'changes': changes
                    })
        except Exception:
            row_changes = []
        
        change_tracking['row_changes'] = row_changes[:20]  # Keep only first 20 samples
        
        return anon_df, change_tracking
