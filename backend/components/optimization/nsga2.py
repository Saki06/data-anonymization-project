"""
NSGA-II Multi-objective Optimization for Privacy-Utility Trade-off
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Any

# Check if pymoo is available
try:
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.core.problem import Problem
    from pymoo.optimize import minimize
    PYMOO_AVAILABLE = True
except ImportError:
    PYMOO_AVAILABLE = False

# Import from anonymization component
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from backend.components.anonymization.methods import AnonymizationMethods


# Use pymoo Problem class if available, otherwise use our own
if PYMOO_AVAILABLE:
    class PrivacyUtilityProblem(Problem):
        """NSGA-II Problem: Optimize privacy-utility trade-off"""
        
        def __init__(self, df: pd.DataFrame, quasi_identifiers: List[str],
                     sensitive_attributes: List[str] = None):
            """Initialize optimization problem"""
            self.df = df
            self.qi_df = df[quasi_identifiers].copy()
            self.quasi_identifiers = quasi_identifiers
            self.sensitive_attributes = sensitive_attributes or []
            
            # Decision variables: [k, l, t, generalization_level]
            # k: 2-20, l: 2-10, t: 0.1-0.5, gen_level: 0-1
            super().__init__(
                n_var=4,
                n_obj=2,
                n_constr=0,
                xl=np.array([2, 2, 0.1, 0.0]),
                xu=np.array([20, 10, 0.5, 1.0])
            )
        
        def _evaluate(self, X, out, *args, **kwargs):
            """Evaluate fitness for each solution"""
            n_pop = X.shape[0]
            privacy_scores = []
            utility_scores = []
            
            for i in range(n_pop):
                k = int(X[i, 0])
                l = int(X[i, 1])
                t = float(X[i, 2])
                gen_level = float(X[i, 3])
                
                # Apply anonymization
                try:
                    anon_df = self.df.copy()
                    
                    # Apply generalization if needed
                    if gen_level > 0.5:
                        for qi in self.quasi_identifiers:
                            if pd.api.types.is_numeric_dtype(anon_df[qi]):
                                anon_df = AnonymizationMethods.generalization(
                                    anon_df, qi, method='numeric_binning', bins=5
                                )
                            else:
                                anon_df = AnonymizationMethods.generalization(
                                    anon_df, qi, method='suppress_rare'
                                )
                    
                    # Apply k-anonymity
                    anon_df = AnonymizationMethods.k_anonymity(
                        anon_df, self.quasi_identifiers, k
                    )
                    
                    # Apply l-diversity if sensitive attributes exist
                    if self.sensitive_attributes:
                        for sens_attr in self.sensitive_attributes:
                            if sens_attr in anon_df.columns:
                                anon_df = AnonymizationMethods.l_diversity(
                                    anon_df, self.quasi_identifiers, sens_attr, l
                                )
                    
                    # Apply t-closeness
                    if self.sensitive_attributes:
                        for sens_attr in self.sensitive_attributes:
                            if sens_attr in anon_df.columns:
                                anon_df = AnonymizationMethods.t_closeness(
                                    anon_df, self.quasi_identifiers, sens_attr, t
                                )
                    
                    # Calculate privacy score
                    privacy_score = self._calculate_privacy_score(anon_df)
                    # Calculate utility score
                    utility_score = self._calculate_utility_score(anon_df)
                    
                    privacy_scores.append(privacy_score)
                    utility_scores.append(utility_score)
                    
                except Exception:
                    privacy_scores.append(1.0)
                    utility_scores.append(1.0)
            
            out["F"] = np.column_stack([privacy_scores, utility_scores])
        
        def _calculate_privacy_score(self, anon_df: pd.DataFrame) -> float:
            qi_df = anon_df[self.quasi_identifiers]
            suppressed = (qi_df == '*').sum().sum()
            total = len(qi_df) * len(self.quasi_identifiers)
            suppression_ratio = suppressed / total if total > 0 else 0
            groups = qi_df.groupby(list(self.quasi_identifiers))
            group_sizes = groups.size()
            min_size = group_sizes.min() if len(group_sizes) > 0 else 0
            privacy_score = (1 - suppression_ratio) * 0.5 + (1 - min(1.0, 1.0 / max(min_size, 1))) * 0.5
            return privacy_score
        
        def _calculate_utility_score(self, anon_df: pd.DataFrame) -> float:
            information_loss = 0.0
            for col in self.quasi_identifiers:
                if col in anon_df.columns and col in self.df.columns:
                    original = self.df[col].dropna()
                    anonymized = anon_df[col].dropna()
                    if len(original) > 0 and len(anonymized) > 0:
                        orig_entropy = self._calculate_entropy(original)
                        anon_entropy = self._calculate_entropy(anonymized)
                        if orig_entropy > 0:
                            loss = 1 - (anon_entropy / orig_entropy)
                            information_loss += loss
            avg_loss = information_loss / len(self.quasi_identifiers) if self.quasi_identifiers else 0
            return avg_loss
        
        def _calculate_entropy(self, series: pd.Series) -> float:
            value_counts = series.value_counts()
            probs = value_counts / len(series)
            probs = probs[probs > 0]
            entropy = -np.sum(probs * np.log2(probs))
            return entropy
else:
    # Fallback class without pymoo
    class PrivacyUtilityProblem:
        def __init__(self, df: pd.DataFrame, quasi_identifiers: List[str],
                     sensitive_attributes: List[str] = None):
            self.df = df
            self.quasi_identifiers = quasi_identifiers
            self.sensitive_attributes = sensitive_attributes or []
        
        def evaluate(self, X: np.ndarray) -> np.ndarray:
            return np.array([[0.5, 0.5]])


class NSGA2Optimizer:
    """NSGA-II optimizer for privacy-utility optimization"""
    
    def __init__(self, population_size: int = 20, n_generations: int = 10):
        self.population_size = population_size
        self.n_generations = n_generations
    
    def optimize(self, df: pd.DataFrame, quasi_identifiers: List[str],
                sensitive_attributes: List[str] = None) -> Dict[str, Any]:
        """Run NSGA-II optimization"""
        
        if not PYMOO_AVAILABLE:
            return self._simple_optimize(df, quasi_identifiers, sensitive_attributes)
        
        try:
            problem = PrivacyUtilityProblem(df, quasi_identifiers, sensitive_attributes)
            algorithm = NSGA2(pop_size=self.population_size)
            
            res = minimize(
                problem,
                algorithm,
                ('n_gen', self.n_generations),
                verbose=False
            )
            
            pareto_front = res.F
            pareto_solutions = res.X
            
            if len(pareto_front) > 0:
                privacy_normalized = (pareto_front[:, 0] - pareto_front[:, 0].min()) / (
                    pareto_front[:, 0].max() - pareto_front[:, 0].min() + 1e-10
                )
                utility_normalized = (pareto_front[:, 1] - pareto_front[:, 1].min()) / (
                    pareto_front[:, 1].max() - pareto_front[:, 1].min() + 1e-10
                )
                
                distances = np.sqrt(privacy_normalized**2 + utility_normalized**2)
                best_idx = np.argmin(distances)
                
                best_solution = pareto_solutions[best_idx]
                best_params = {
                    'k': int(best_solution[0]),
                    'l': int(best_solution[1]),
                    't': float(best_solution[2]),
                    'generalization_level': float(best_solution[3])
                }
            else:
                best_params = {'k': 5, 'l': 2, 't': 0.2, 'generalization_level': 0.5}
            
            return {
                'optimal_parameters': best_params,
                'pareto_front': pareto_front.tolist() if len(pareto_front) > 0 else [],
                'pareto_solutions': pareto_solutions.tolist() if len(pareto_solutions) > 0 else [],
                'optimization_success': True
            }
        except Exception as e:
            print(f"[WARNING] NSGA-II optimization failed, using simple optimization: {e}")
            return self._simple_optimize(df, quasi_identifiers, sensitive_attributes)
    
    def _simple_optimize(self, df: pd.DataFrame, quasi_identifiers: List[str],
                         sensitive_attributes: List[str] = None) -> Dict[str, Any]:
        """Simple fallback optimization without pymoo"""
        
        test_params = [
            {'k': 5, 'l': 2, 't': 0.2, 'generalization_level': 0.5},
            {'k': 5, 'l': 3, 't': 0.1, 'generalization_level': 0.3},
            {'k': 10, 'l': 2, 't': 0.2, 'generalization_level': 0.5},
            {'k': 3, 'l': 2, 't': 0.3, 'generalization_level': 0.7},
        ]
        
        best_score = float('inf')
        best_params = test_params[0]
        
        # Simple evaluation
        for params in test_params:
            k = params['k']
            l = params['l']
            t = params['t']
            gen_level = params['generalization_level']
            
            try:
                anon_df = df.copy()
                
                if gen_level > 0.5:
                    for qi in quasi_identifiers:
                        if pd.api.types.is_numeric_dtype(anon_df[qi]):
                            anon_df = AnonymizationMethods.generalization(
                                anon_df, qi, method='numeric_binning', bins=5
                            )
                        else:
                            anon_df = AnonymizationMethods.generalization(
                                anon_df, qi, method='suppress_rare'
                            )
                
                anon_df = AnonymizationMethods.k_anonymity(anon_df, quasi_identifiers, k)
                
                if sensitive_attributes:
                    for sens_attr in sensitive_attributes:
                        if sens_attr in anon_df.columns:
                            anon_df = AnonymizationMethods.l_diversity(
                                anon_df, quasi_identifiers, sens_attr, l
                            )
                
                # Calculate scores
                qi_df = anon_df[quasi_identifiers]
                suppressed = (qi_df == '*').sum().sum()
                total = len(qi_df) * len(quasi_identifiers)
                suppression_ratio = suppressed / total if total > 0 else 0
                
                groups = qi_df.groupby(list(quasi_identifiers))
                group_sizes = groups.size()
                min_size = group_sizes.min() if len(group_sizes) > 0 else 1
                
                privacy_score = (1 - suppression_ratio) * 0.5 + (1 - min(1.0, 1.0 / max(min_size, 1))) * 0.5
                utility_score = suppression_ratio  # Simple utility score
                
                score = privacy_score + utility_score
                
                if score < best_score:
                    best_score = score
                    best_params = params.copy()
                    
            except Exception:
                continue
        
        return {
            'optimal_parameters': best_params,
            'pareto_front': [],
            'pareto_solutions': [],
            'optimization_success': True
        }

