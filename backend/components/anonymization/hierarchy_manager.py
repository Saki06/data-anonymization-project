"""
Generalization Hierarchy Manager

This module implements scientifically acceptable hierarchical generalization
for SDC (Statistical Disclosure Control) systems.

It provides:
- Storage of hierarchical generalization trees
- Tracking of generalization levels per attribute
- Support for monotonic transformations
- Lattice search algorithms for Mondrian-style partitioning

Example hierarchies:
- Age: 27 → 25-29 → 20-29 → 20-39 → *
- Geography: Colombo 7 → Colombo → Western Province → Sri Lanka → *
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Optional, Set
from collections import defaultdict
import json


class GeneralizationHierarchy:
    """
    Represents a single generalization hierarchy for an attribute.
    
    A hierarchy is a tree where leaf nodes are original values and
    higher levels represent more generalized values.
    """
    
    def __init__(self, attribute_name: str):
        self.attribute_name = attribute_name
        self.levels: Dict[int, Dict[str, Set[str]]] = {}  # level -> {general -> set of original valuesized_value}
        self.max_level: int = 0
        self.value_to_path: Dict[str, List[str]] = {}  # original value -> path from leaf to root
        
    def add_level(self, level: int, mapping: Dict[str, List[str]]):
        """
        Add a generalization level.
        
        Args:
            level: The hierarchy level (0 = original values, higher = more generalized)
            mapping: Dict mapping generalized values to lists of original values they contain
        """
        if level > self.max_level:
            self.max_level = level
            
        self.levels[level] = {}
        for gen_value, orig_values in mapping.items():
            self.levels[level][gen_value] = set(orig_values)
            for orig in orig_values:
                if orig not in self.value_to_path:
                    self.value_to_path[orig] = []
                self.value_to_path[orig].append(gen_value)
    
    def generalize(self, value: str, target_level: int) -> str:
        """
        Generalize a value to a specific level.
        
        Args:
            value: Original value
            target_level: Target hierarchy level
            
        Returns:
            Generalized value at target level
        """
        if value not in self.value_to_path:
            return value  # Unknown value, return as-is
            
        path = self.value_to_path[value]
        if target_level >= len(path):
            return path[-1]  # Return highest level available
            
        return path[target_level]
    
    def get_level(self, value: str) -> int:
        """
        Get the current generalization level of a value.
        
        Args:
            value: The value to check
            
        Returns:
            Current level (0 = most specific)
        """
        if value not in self.value_to_path:
            return 0
        return len(self.value_to_path[value]) - 1
    
    def get_values_at_level(self, level: int) -> Set[str]:
        """
        Get all distinct values at a specific level.
        
        Args:
            level: The hierarchy level
            
        Returns:
            Set of values at that level
        """
        if level not in self.levels:
            return set()
        return set(self.levels[level].keys())
    
    def can_generalize_more(self, value: str) -> bool:
        """Check if a value can be generalized further."""
        if value not in self.value_to_path:
            return False
        return len(self.value_to_path[value]) < self.max_level + 1


class GeneralizationHierarchyManager:
    """
    Manages generalization hierarchies for multiple attributes.
    
    Responsibilities:
    - Store hierarchies for different attribute types
    - Track generalization levels per attribute
    - Support monotonic transformations
    - Enable lattice search algorithms
    
    This is required for algorithms like Mondrian that use
    hierarchical partitioning for k-anonymity.
    """
    
    def __init__(self):
        self.hierarchies: Dict[str, GeneralizationHierarchy] = {}
        self.current_levels: Dict[str, int] = {}  # attribute -> current generalization level
        self.default_hierarchies_loaded = False
        
    def _load_default_hierarchies(self):
        """Load default hierarchy templates."""
        from .hierarchy_templates import get_default_templates
        templates = get_default_templates()
        for attr_type, template in templates.items():
            self.add_hierarchy_from_template(attr_type, template)
        self.default_hierarchies_loaded = True
    
    def add_hierarchy(self, hierarchy: GeneralizationHierarchy):
        """Add a pre-built hierarchy."""
        self.hierarchies[hierarchy.attribute_name] = hierarchy
        self.current_levels[hierarchy.attribute_name] = 0
    
    def add_hierarchy_from_template(self, attribute_name: str, template: Dict):
        """
        Add a hierarchy from a template definition.
        
        Args:
            attribute_name: Name of the attribute
            template: Dict with 'levels' key containing level definitions
        """
        hierarchy = GeneralizationHierarchy(attribute_name)
        
        for level_idx, level_data in enumerate(template.get('levels', [])):
            mapping = level_data.get('mapping', {})
            hierarchy.add_level(level_idx, mapping)
            
        self.hierarchies[attribute_name] = hierarchy
        self.current_levels[attribute_name] = 0
    
    def get_hierarchy(self, attribute_name: str) -> Optional[GeneralizationHierarchy]:
        """Get the hierarchy for an attribute."""
        return self.hierarchies.get(attribute_name)
    
    def set_level(self, attribute_name: str, level: int) -> bool:
        """
        Set the generalization level for an attribute.
        
        Args:
            attribute_name: Name of the attribute
            level: Target level (must be >= current level for monotonicity)
            
        Returns:
            True if level was set successfully
        """
        if attribute_name not in self.hierarchies:
            return False
            
        current = self.current_levels.get(attribute_name, 0)
        if level < current:
            return False  # Monotonicity violation
            
        max_level = self.hierarchies[attribute_name].max_level
        self.current_levels[attribute_name] = min(level, max_level)
        return True
    
    def get_level(self, attribute_name: str) -> int:
        """Get current generalization level for an attribute."""
        return self.current_levels.get(attribute_name, 0)
    
    def get_max_level(self, attribute_name: str) -> int:
        """Get maximum level for an attribute."""
        if attribute_name not in self.hierarchies:
            return 0
        return self.hierarchies[attribute_name].max_level
    
    def generalize_value(self, attribute_name: str, value: Any, target_level: Optional[int] = None) -> str:
        """
        Generalize a single value using the hierarchy.
        
        Args:
            attribute_name: Name of the attribute
            value: Original value
            target_level: Target level (if None, uses current level)
            
        Returns:
            Generalized value
        """
        if attribute_name not in self.hierarchies:
            return str(value)
            
        if target_level is None:
            target_level = self.current_levels.get(attribute_name, 0)
            
        hierarchy = self.hierarchies[attribute_name]
        
        # Convert value to string for lookup
        str_value = str(value)
        return hierarchy.generalize(str_value, target_level)
    
    def generalize_column(self, df: pd.DataFrame, column: str, target_level: Optional[int] = None) -> pd.DataFrame:
        """
        Generalize all values in a column.
        
        Args:
            df: Input dataframe
            column: Column name
            target_level: Target level (if None, uses current level)
            
        Returns:
            DataFrame with generalized column
        """
        result_df = df.copy()
        
        if column not in self.hierarchies:
            return result_df
            
        if target_level is None:
            target_level = self.current_levels.get(column, 0)
            
        hierarchy = self.hierarchies[column]
        
        # Apply generalization to each value
        result_df[column] = result_df[column].apply(
            lambda v: hierarchy.generalize(str(v), target_level)
        )
        
        return result_df
    
    def get_partition_candidates(self, df: pd.DataFrame, quasi_identifiers: List[str]) -> List[Tuple[str, Any]]:
        """
        Get candidate partition points for Mondrian-style partitioning.
        
        For each QI attribute, returns possible split points based on
        the hierarchy levels.
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            
        Returns:
            List of (attribute, split_value) tuples representing partition points
        """
        candidates = []
        
        for qi in quasi_identifiers:
            if qi not in self.hierarchies:
                continue
                
            hierarchy = self.hierarchies[qi]
            current_level = self.current_levels.get(qi, 0)
            
            # Can only partition at current level or deeper
            if current_level < hierarchy.max_level:
                # Get distinct values at current level
                current_values = hierarchy.get_values_at_level(current_level)
                
                # For each value, find the next generalization level
                for val in current_values:
                    # Get original values that map to this generalized value
                    if current_level in hierarchy.levels:
                        orig_values = hierarchy.levels[current_level].get(val, set())
                        if len(orig_values) > 1:
                            # Can potentially split this group
                            candidates.append((qi, val))
        
        return candidates
    
    def create_numeric_hierarchy(
        self,
        attribute_name: str,
        min_val: float,
        max_val: float,
        num_levels: int = 4,
        range_type: str = 'equal_width'
    ) -> GeneralizationHierarchy:
        """
        Create a numeric hierarchy for an attribute.
        
        Args:
            attribute_name: Name of the attribute
            min_val: Minimum value in the data
            max_val: Maximum value in the data
            num_levels: Number of hierarchy levels
            range_type: 'equal_width' or 'equal_frequency'
            
        Returns:
            Created hierarchy
        """
        hierarchy = GeneralizationHierarchy(attribute_name)
        
        # Level 0: Original values (identity)
        # This is implicit - no mapping needed
        
        if range_type == 'equal_width':
            # Create equal-width bins for each level
            for level in range(1, num_levels + 1):
                num_bins = max(2, 2 ** (level - 1))
                bin_width = (max_val - min_val) / num_bins
                
                mapping = {}
                for i in range(num_bins):
                    low = min_val + i * bin_width
                    high = min_val + (i + 1) * bin_width
                    bin_label = f"{int(low)}-{int(high)}"
                    
                    # Get all values in this range
                    orig_values = []
                    for v in np.arange(low, high + 0.001, (bin_width / 10) if bin_width > 1 else 0.1):
                        if v >= low and v < high:
                            orig_values.append(str(int(v)) if bin_width > 1 else f"{v:.1f}")
                    
                    # Use numeric ranges as keys
                    mapping[bin_label] = [str(int(low + j)) for j in range(int(low), int(high) + 1)]
                
                hierarchy.add_level(level, mapping)
                
        elif range_type == 'equal_frequency':
            # This would need actual data to compute quantiles
            # For now, fall back to equal width
            return self.create_numeric_hierarchy(
                attribute_name, min_val, max_val, num_levels, 'equal_width'
            )
        
        self.hierarchies[attribute_name] = hierarchy
        self.current_levels[attribute_name] = 0
        return hierarchy
    
    def create_categorical_hierarchy(
        self,
        attribute_name: str,
        category_groups: Dict[str, List[str]]
    ) -> GeneralizationHierarchy:
        """
        Create a categorical hierarchy from category groupings.
        
        Args:
            attribute_name: Name of the attribute
            category_groups: Dict mapping generalized categories to lists of original categories
            
        Returns:
            Created hierarchy
        """
        hierarchy = GeneralizationHierarchy(attribute_name)
        
        # Level 0: Original categories (identity) - implicit
        
        # Level 1: First level of grouping
        mapping = {}
        for gen_cat, orig_cats in category_groups.items():
            mapping[gen_cat] = [str(c) for c in orig_cats]
        hierarchy.add_level(1, mapping)
        
        # Level 2: Suppress to '*' (maximum generalization)
        level2_mapping = {'*': list(category_groups.values())}
        hierarchy.add_level(2, level2_mapping)
        
        self.hierarchies[attribute_name] = hierarchy
        self.current_levels[attribute_name] = 0
        return hierarchy
    
    def apply_mondrian_partition(
        self,
        df: pd.DataFrame,
        quasi_identifiers: List[str],
        k: int
    ) -> List[pd.DataFrame]:
        """
        Apply Mondrian-style partition using hierarchies.
        
        This is a simplified implementation that uses the generalization
        levels to create partitions.
        
        Args:
            df: Input dataframe
            quasi_identifiers: List of QI column names
            k: k-anonymity parameter
            
        Returns:
            List of partitions (dataframes)
        """
        # Start with full dataset as one partition
        partitions = [df]
        
        # Try to partition until no more valid splits possible
        changed = True
        while changed:
            changed = False
            new_partitions = []
            
            for partition in partitions:
                # Check if partition already satisfies k-anonymity
                if len(partition) < k:
                    new_partitions.append(partition)
                    continue
                
                # Try to find a QI to partition on
                best_partition = None
                best_score = -1
                
                for qi in quasi_identifiers:
                    if qi not in self.hierarchies:
                        continue
                    
                    hierarchy = self.hierarchies[qi]
                    current_level = self.current_levels.get(qi, 0)
                    
                    if current_level >= hierarchy.max_level:
                        continue
                    
                    # Get unique values at current level
                    unique_values = partition[qi].unique()
                    
                    if len(unique_values) <= 1:
                        continue
                    
                    # Try splitting by value
                    for val in unique_values:
                        subset1 = partition[partition[qi] == val]
                        subset2 = partition[partition[qi] != val]
                        
                        # Check if both subsets satisfy k
                        if len(subset1) >= k and len(subset2) >= k:
                            # Calculate score (prefer balanced splits)
                            balance = min(len(subset1), len(subset2)) / max(len(subset1), len(subset2))
                            if balance > best_score:
                                best_score = balance
                                best_partition = (subset1, subset2, qi)
                                break
                    
                    if best_partition:
                        break
                
                if best_partition:
                    subset1, subset2, qi = best_partition
                    new_partitions.extend([subset1, subset2])
                    changed = True
                else:
                    new_partitions.append(partition)
            
            partitions = new_partitions
        
        return partitions
    
    def to_dict(self) -> Dict:
        """Export hierarchy configuration to dict."""
        result = {}
        for attr_name, hierarchy in self.hierarchies.items():
            result[attr_name] = {
                'current_level': self.current_levels.get(attr_name, 0),
                'max_level': hierarchy.max_level,
                'levels': {}
            }
            for level, values in hierarchy.levels.items():
                result[attr_name]['levels'][level] = {
                    k: list(v) for k, v in values.items()
                }
        return result
    
    def from_dict(self, data: Dict):
        """Import hierarchy configuration from dict."""
        self.hierarchies.clear()
        self.current_levels.clear()
        
        for attr_name, attr_data in data.items():
            hierarchy = GeneralizationHierarchy(attr_name)
            
            for level, values in attr_data.get('levels', {}).items():
                hierarchy.add_level(level, values)
            
            self.hierarchies[attr_name] = hierarchy
            self.current_levels[attr_name] = attr_data.get('current_level', 0)


# Global instance for use across the application
_global_hierarchy_manager = None

def get_hierarchy_manager() -> GeneralizationHierarchyManager:
    """Get or create the global hierarchy manager instance."""
    global _global_hierarchy_manager
    if _global_hierarchy_manager is None:
        _global_hierarchy_manager = GeneralizationHierarchyManager()
        _global_hierarchy_manager._load_default_hierarchies()
    return _global_hierarchy_manager


def reset_hierarchy_manager():
    """Reset the global hierarchy manager (useful for testing)."""
    global _global_hierarchy_manager
    _global_hierarchy_manager = None
