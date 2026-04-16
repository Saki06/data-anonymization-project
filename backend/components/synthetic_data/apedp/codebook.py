"""
Codebook Mapping Module
Supports optional codebook JSON file upload to create label columns.
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd
import json


def load_codebook(codebook_path: Optional[str] = None) -> Optional[Dict]:
    """
    Load codebook from JSON file.
    
    Args:
        codebook_path: Path to codebook JSON file
        
    Returns:
        Dictionary mapping column names to value mappings, or None
    """
    if codebook_path is None:
        return None
    
    try:
        with open(codebook_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to load codebook: {e}")


def apply_codebook(df: pd.DataFrame, codebook: Optional[Dict] = None) -> Tuple[pd.DataFrame, List[str]]:
    """
    Apply codebook mappings to create label columns.
    
    Args:
        df: Input DataFrame
        codebook: Dictionary mapping column names to value mappings
        
    Returns:
        Tuple of (DataFrame with added *_lbl columns, list of mapped column names)
    """
    if codebook is None:
        return df, []
    
    df_result = df.copy()
    mapped_columns = []
    
    for col, mapping in codebook.items():
        if col not in df.columns:
            continue
        
        label_col = f"{col}_lbl"
        col_series = df[col]
        col_dtype = col_series.dtype
        
        if pd.api.types.is_numeric_dtype(col_dtype):
            numeric_mapping = {}
            for k, v in mapping.items():
                try:
                    if isinstance(k, str) and k.isdigit():
                        if col_series.dtype == 'object' or any(isinstance(x, str) for x in col_series.dropna().head(10)):
                            numeric_mapping[str(k)] = v
                        else:
                            numeric_mapping[float(k)] = v
                    else:
                        numeric_mapping[k] = v
                except:
                    numeric_mapping[k] = v
            mapping_to_use = numeric_mapping
        else:
            mapping_to_use = mapping
        
        try:
            if col_series.dtype == 'object':
                df_result[label_col] = df_result[col].astype(str).map(mapping_to_use)
            else:
                df_result[label_col] = df_result[col].map(mapping_to_use)
                if df_result[label_col].isna().all():
                    df_result[label_col] = df_result[col].astype(str).map(mapping_to_use)
        except Exception as e:
            print(f"Warning: Failed to map column {col}: {e}")
            continue
        
        mapped_columns.append(col)
    
    return df_result, mapped_columns
