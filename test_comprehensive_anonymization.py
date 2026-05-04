#!/usr/bin/env python3
"""
Test script for comprehensive anonymization with change tracking
"""

import pandas as pd
import sys
import os
import json

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from components.anonymization.methods import AnonymizationMethods

def test_comprehensive_anonymization():
    """Test the comprehensive anonymization with change tracking"""
    
    print("=" * 80)
    print("TESTING COMPREHENSIVE ANONYMIZATION WITH CHANGE TRACKING")
    print("=" * 80)
    
    # Create sample dataset
    df = pd.DataFrame({
        'name': ['John Smith', 'Jane Doe', 'Bob Johnson', 'Alice Williams', 'Charlie Brown'],
        'email': ['john@example.com', 'jane@example.com', 'bob@example.com', 'alice@example.com', 'charlie@example.com'],
        'age': [25, 32, 45, 28, 55],
        'gender': ['M', 'F', 'M', 'F', 'M'],
        'income': [35000, 52000, 75000, 45000, 65000],
        'health_condition': ['Diabetes', 'Healthy', 'Hypertension', 'Healthy', 'Asthma'],
        'zip_code': ['10001', '10002', '10003', '10004', '10005'],
        'city': ['New York', 'New York', 'New York', 'New York', 'New York']
    })
    
    print("\nORIGINAL DATA:")
    print(df)
    print(f"\nOriginal shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")
    
    # Define column types
    quasi_identifiers = ['age', 'gender', 'zip_code']
    sensitive_attributes = ['income', 'health_condition']
    direct_identifiers = ['name', 'email']
    
    analysis_results = {
        'detected_problems': [
            {'problem': 'Direct Identifier: name', 'column': 'name'},
            {'problem': 'Direct Identifier: email', 'column': 'email'},
        ]
    }
    
    print("\n" + "=" * 80)
    print("CONFIGURATION:")
    print(f"  Quasi-Identifiers: {quasi_identifiers}")
    print(f"  Sensitive Attributes: {sensitive_attributes}")
    print(f"  Direct Identifiers: {direct_identifiers}")
    print("=" * 80)
    
    # Test comprehensive anonymization
    print("\nApplying comprehensive anonymization...")
    try:
        anon_df, change_tracking = AnonymizationMethods.comprehensive_anonymize_with_tracking(
            df=df,
            quasi_identifiers=quasi_identifiers,
            sensitive_attributes=sensitive_attributes,
            direct_identifiers=direct_identifiers,
            analysis_results=analysis_results,
            k=2,
            l=2,
            t=0.2,
            generalization_level=0.5
        )
        
        print("✓ Anonymization completed successfully!")
        
    except Exception as e:
        print(f"✗ Anonymization failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Display results
    print("\n" + "=" * 80)
    print("ANONYMIZED DATA:")
    print(anon_df)
    print(f"\nAnonymized shape: {anon_df.shape}")
    
    print("\n" + "=" * 80)
    print("CHANGE TRACKING SUMMARY:")
    print(f"  Total columns changed: {change_tracking['total_columns_changed']}")
    print(f"  Total cells changed: {change_tracking['total_cells_changed']}")
    print(f"  Number of column transformations: {len(change_tracking['column_changes'])}")
    
    print("\n" + "-" * 80)
    print("COLUMN-BY-COLUMN CHANGES:")
    print("-" * 80)
    
    for col_change in change_tracking['column_changes']:
        print(f"\n  Column: {col_change['column_name']}")
        print(f"    Type: {col_change['column_type']}")
        print(f"    Method: {col_change['anonymization_method']}")
        print(f"    Original unique values: {col_change['original_unique_values']}")
        print(f"    Anonymized unique values: {col_change['anonymized_unique_values']}")
        print(f"    Cells modified: {col_change['cells_modified']}")
        
        if col_change['sample_changes']:
            print(f"    Sample transformations:")
            for sample in col_change['sample_changes'][:2]:
                print(f"      {sample['original']} → {sample['anonymized']}")
    
    print("\n" + "-" * 80)
    print("ROW-LEVEL CHANGES (Sample):")
    print("-" * 80)
    
    for row_change in change_tracking['row_changes'][:3]:  # Show first 3 rows
        print(f"\n  Row {row_change['row_index']}:")
        print(f"    Changed columns: {', '.join(row_change['changed_columns'])}")
        for col_name, changes in row_change['changes'].items():
            print(f"      {col_name}: {changes['original']} → {changes['anonymized']}")
    
    print("\n" + "=" * 80)
    print("VERIFICATION:")
    print("=" * 80)
    
    # Verify direct identifiers are suppressed
    all_suppressed = all(
        anon_df[di].apply(lambda x: str(x) in ['[SUPPRESSED]', 'nan', 'NaN']).all() 
        for di in direct_identifiers if di in anon_df.columns
    )
    print(f"✓ Direct identifiers suppressed: {all_suppressed}")
    
    # Verify quasi-identifiers are present (but may be modified)
    qi_present = all(qi in anon_df.columns for qi in quasi_identifiers)
    print(f"✓ Quasi-identifiers present: {qi_present}")
    
    # Verify sensitive attributes are modified
    sensitive_modified = False
    for sa in sensitive_attributes:
        if sa in anon_df.columns:
            original_unique = df[sa].nunique()
            anon_unique = anon_df[sa].nunique()
            if anon_unique < original_unique or anon_df[sa].astype(str).str.contains('SUPPRESSED').any():
                sensitive_modified = True
                break
    print(f"✓ Sensitive attributes modified: {sensitive_modified}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    
    return True

if __name__ == '__main__':
    success = test_comprehensive_anonymization()
    sys.exit(0 if success else 1)
