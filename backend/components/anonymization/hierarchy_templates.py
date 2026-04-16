"""
Hierarchy Templates for Common Attribute Types

This module provides pre-defined generalization hierarchies
for common attribute types used in SDC anonymization.

Each template follows the structure:
{
    'attribute_type': 'type_name',
    'description': 'description of the hierarchy',
    'levels': [
        {
            'level': 0,
            'description': 'Original values (identity)',
            'mapping': {}  # Identity mapping (implicit)
        },
        {
            'level': 1,
            'description': 'First generalization level',
            'mapping': {'generalized_value': ['original_value1', 'original_value2', ...]}
        },
        ...
    ]
}
"""

from typing import Dict, List, Any, Optional


def get_age_hierarchy_template() -> Dict:
    """
    Age hierarchy based on standard SDC practices.
    
    Levels:
    0: Exact age (e.g., 27)
    1: 5-year ranges (e.g., 25-29)
    2: 10-year ranges (e.g., 20-29)
    3: 20-year ranges (e.g., 20-39)
    4: Suppressed (*)
    """
    levels = []
    
    # Level 0 is implicit (identity)
    levels.append({
        'level': 0,
        'description': 'Exact age values',
        'mapping': {}
    })
    
    # Level 1: 5-year ranges
    level1_mapping = {}
    for start in range(0, 100, 5):
        end = start + 4
        key = f"{start}-{end}"
        values = [str(i) for i in range(start, min(end + 1, 100))]
        level1_mapping[key] = values
    levels.append({
        'level': 1,
        'description': '5-year age ranges',
        'mapping': level1_mapping
    })
    
    # Level 2: 10-year ranges
    level2_mapping = {}
    for start in range(0, 100, 10):
        end = start + 9
        key = f"{start}-{end}"
        values = [str(i) for i in range(start, min(end + 1, 100))]
        level2_mapping[key] = values
    levels.append({
        'level': 2,
        'description': '10-year age ranges',
        'mapping': level2_mapping
    })
    
    # Level 3: 20-year ranges
    level3_mapping = {}
    for start in range(0, 100, 20):
        end = start + 19
        key = f"{start}-{end}"
        values = [str(i) for i in range(start, min(end + 1, 100))]
        level3_mapping[key] = values
    levels.append({
        'level': 3,
        'description': '20-year age ranges',
        'mapping': level3_mapping
    })
    
    # Level 4: Very broad ranges (instead of suppression)
    level4_mapping = {
        '0-49': [str(i) for i in range(0, 50)],
        '50-99': [str(i) for i in range(50, 100)]
    }
    levels.append({
        'level': 4,
        'description': '50-year age ranges',
        'mapping': level4_mapping
    })
    
    return {
        'attribute_type': 'age',
        'description': 'Age generalization hierarchy with 5-year, 10-year, and 20-year ranges',
        'levels': levels
    }


def get_geography_hierarchy_template() -> Dict:
    """
    Geography hierarchy for Sri Lanka (as mentioned in problem_1.md).
    
    Levels:
    0: Exact location (e.g., Colombo 7)
    1: City/District (e.g., Colombo)
    2: Province (e.g., Western Province)
    3: Country (e.g., Sri Lanka)
    4: Suppressed (*)
    """
    levels = []
    
    # Level 0 is implicit (identity)
    levels.append({
        'level': 0,
        'description': 'Exact location',
        'mapping': {}
    })
    
    # Level 1: City to District mapping (Sri Lanka specific)
    level1_mapping = {
        'Colombo': ['Colombo 1', 'Colombo 2', 'Colombo 3', 'Colombo 4', 'Colombo 5', 
                    'Colombo 6', 'Colombo 7', 'Colombo 8', 'Colombo 9', 'Colombo 10',
                    'Colombo 11', 'Colombo 12', 'Colombo 13', 'Colombo 14', 'Colombo 15'],
        'Kandy': ['Kandy', 'Kandy North', 'Kandy South'],
        'Galle': ['Galle', 'Galle North', 'Galle South'],
        'Jaffna': ['Jaffna', 'Jaffna North', 'Jaffna South'],
        'Kurunegala': ['Kurunegala', 'Kurunegala North', 'Kurunegala South'],
        'Anuradhapura': ['Anuradhapura', 'Anuradhapura East', 'Anuradhapura West'],
        'Ratnapura': ['Ratnapura', 'Ratnapura North', 'Ratnapura South'],
        'Matale': ['Matale', 'Matale North', 'Matale South'],
        'Nuwara Eliya': ['Nuwara Eliya', 'Nuwara Eliya West', 'Nuwara Eliya East'],
        'Gampaha': ['Gampaha', 'Gampaha North', 'Gampaha South', 'Negombo', 'Katana']
    }
    levels.append({
        'level': 1,
        'description': 'City/District level',
        'mapping': level1_mapping
    })
    
    # Level 2: Province level
    level2_mapping = {
        'Western Province': ['Colombo', 'Gampaha', 'Kalutara'],
        'Central Province': ['Kandy', 'Matale', 'Nuwara Eliya'],
        'Southern Province': ['Galle', 'Matara', 'Hambantota'],
        'Northern Province': ['Jaffna', 'Kilinochchi', 'Mannar', 'Mullaitivu', 'Vanni'],
        'Eastern Province': ['Batticaloa', 'Trincomalee', 'Ampara'],
        'North Central Province': ['Anuradhapura', 'Polonnaruwa'],
        'Sabaragamuwa Province': ['Ratnapura', 'Kegalle'],
        'Uva Province': ['Badulla', 'Moneragala'],
        'North Western Province': ['Kurunegala', 'Puttalam']
    }
    levels.append({
        'level': 2,
        'description': 'Province level',
        'mapping': level2_mapping
    })
    
    # Level 3: Country level
    level3_mapping = {
        'Sri Lanka': list(level2_mapping.keys())
    }
    levels.append({
        'level': 3,
        'description': 'Country level',
        'mapping': level3_mapping
    })
    
    # Level 4: Continent level (instead of suppression)
    level4_mapping = {
        'Asia': ['Sri Lanka']
    }
    levels.append({
        'level': 4,
        'description': 'Continent level',
        'mapping': level4_mapping
    })
    
    return {
        'attribute_type': 'geography',
        'description': 'Geography hierarchy (Sri Lanka): City -> Province -> Country',
        'levels': levels
    }


def get_date_hierarchy_template() -> Dict:
    """
    Date/time hierarchy.
    
    Levels:
    0: Exact date
    1: Day of month
    2: Month
    3: Year
    4: Decade
    5: Suppressed
    """
    levels = []
    
    # Level 0 is implicit (identity)
    levels.append({
        'level': 0,
        'description': 'Exact date',
        'mapping': {}
    })
    
    # Level 1: Day of month groups
    level1_mapping = {
        '1-7': ['1', '2', '3', '4', '5', '6', '7'],
        '8-14': ['8', '9', '10', '11', '12', '13', '14'],
        '15-21': ['15', '16', '17', '18', '19', '20', '21'],
        '22-31': ['22', '23', '24', '25', '26', '27', '28', '29', '30', '31']
    }
    levels.append({
        'level': 1,
        'description': 'Week of month',
        'mapping': level1_mapping
    })
    
    # Level 2: Month
    months = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']
    level2_mapping = {m: [str(i+1)] for i, m in enumerate(months)}
    levels.append({
        'level': 2,
        'description': 'Month',
        'mapping': level2_mapping
    })
    
    # Level 3: Year
    level3_mapping = {}
    for year in range(1950, 2030):
        level3_mapping[str(year)] = [str(year)]
    level3_mapping_grouped = {}
    for year in range(1950, 2030):
        decade = str(year)[:3] + '0s'
        if decade not in level3_mapping_grouped:
            level3_mapping_grouped[decade] = []
        level3_mapping_grouped[decade].append(str(year))
    levels.append({
        'level': 3,
        'description': 'Year',
        'mapping': level3_mapping
    })
    
    # Level 4: Decade
    level4_mapping = {
        '1950s': [str(y) for y in range(1950, 1960)],
        '1960s': [str(y) for y in range(1960, 1970)],
        '1970s': [str(y) for y in range(1970, 1980)],
        '1980s': [str(y) for y in range(1980, 1990)],
        '1990s': [str(y) for y in range(1990, 2000)],
        '2000s': [str(y) for y in range(2000, 2010)],
        '2010s': [str(y) for y in range(2010, 2020)],
        '2020s': [str(y) for y in range(2020, 2030)]
    }
    levels.append({
        'level': 4,
        'description': 'Decade',
        'mapping': level4_mapping
    })
    
    # Level 5: Century
    levels.append({
        'level': 5,
        'description': 'Century',
        'mapping': {
            '1900s': [str(y) for y in range(1900, 2000)],
            '2000s': [str(y) for y in range(2000, 2100)]
        }
    })
    
    return {
        'attribute_type': 'date',
        'description': 'Date hierarchy: Day -> Month -> Year -> Decade',
        'levels': levels
    }


def get_income_hierarchy_template() -> Dict:
    """
    Income/ Salary hierarchy based on standard ranges.
    
    Levels:
    0: Exact income
    1: Income ranges (e.g., 0-10000)
    2: Broader ranges (e.g., 0-50000)
    3: Very broad (e.g., 0-100000)
    4: Suppressed
    """
    levels = []
    
    # Level 0 is implicit (identity)
    levels.append({
        'level': 0,
        'description': 'Exact income',
        'mapping': {}
    })
    
    # Level 1: $10k ranges
    level1_mapping = {}
    for start in range(0, 200000, 10000):
        end = start + 9999
        key = f"${start:,}-${end:,}"
        level1_mapping[key] = [str(start + i) for i in range(10000)]
    levels.append({
        'level': 1,
        'description': '$10k income ranges',
        'mapping': level1_mapping
    })
    
    # Level 2: $25k ranges
    level2_mapping = {}
    for start in range(0, 200000, 25000):
        end = start + 24999
        key = f"${start:,}-${end:,}"
        level2_mapping[key] = [str(start + i) for i in range(25000)]
    levels.append({
        'level': 2,
        'description': '$25k income ranges',
        'mapping': level2_mapping
    })
    
    # Level 3: $50k ranges
    level3_mapping = {}
    for start in range(0, 200000, 50000):
        end = start + 49999
        key = f"${start:,}-${end:,}"
        level3_mapping[key] = [str(start + i) for i in range(50000)]
    levels.append({
        'level': 3,
        'description': '$50k income ranges',
        'mapping': level3_mapping
    })
    
    # Level 4: Very broad income categories
    levels.append({
        'level': 4,
        'description': 'Broad income categories',
        'mapping': {
            '$0-99,999': [str(i) for i in range(0, 100000)],
            '$100,000+': [str(i) for i in range(100000, 200000)]
        }
    })
    
    return {
        'attribute_type': 'income',
        'description': 'Income hierarchy: $10k -> $25k -> $50k ranges',
        'levels': levels
    }


def get_zipcode_hierarchy_template() -> Dict:
    """
    Zip code / Postal code hierarchy for US-style 5-digit zip codes.
    
    Levels:
    0: Exact zip code (e.g., 12345)
    1: Zip code prefix (e.g., 123**)
    2: Area code (e.g., 12***)
    3: Region (e.g., 1****)
    4: Suppressed (*)
    """
    levels = []
    
    # Level 0 is implicit (identity)
    levels.append({
        'level': 0,
        'description': 'Exact zip code',
        'mapping': {}
    })
    
    # Level 1: Last 2 digits masked (123**)
    level1_mapping = {}
    for prefix in range(10000, 99999, 100):
        key = f"{prefix//100:03d}**"
        values = [f"{prefix + i:05d}" for i in range(100)]
        level1_mapping[key] = values
    levels.append({
        'level': 1,
        'description': 'Zip code prefix (last 2 digits masked)',
        'mapping': level1_mapping
    })
    
    # Level 2: Last 3 digits masked (12***)
    level2_mapping = {}
    for prefix in range(10000, 99999, 1000):
        key = f"{prefix//1000:02d}***"
        values = [f"{prefix + i:05d}" for i in range(1000)]
        level2_mapping[key] = values
    levels.append({
        'level': 2,
        'description': 'Area code (last 3 digits masked)',
        'mapping': level2_mapping
    })
    
    # Level 3: Last 4 digits masked (1****)
    level3_mapping = {}
    for prefix in range(10000, 99999, 10000):
        key = f"{prefix//10000:01d}****"
        values = [f"{prefix + i:05d}" for i in range(10000)]
        level3_mapping[key] = values
    levels.append({
        'level': 3,
        'description': 'Region (last 4 digits masked)',
        'mapping': level3_mapping
    })
    
    # Level 4: Very broad (first digit only)
    level4_mapping = {
        '0****': [f"{i:05d}" for i in range(0, 10000)],
        '1****': [f"{i:05d}" for i in range(10000, 20000)],
        '2****': [f"{i:05d}" for i in range(20000, 30000)],
        '3****': [f"{i:05d}" for i in range(30000, 40000)],
        '4****': [f"{i:05d}" for i in range(40000, 50000)],
        '5****': [f"{i:05d}" for i in range(50000, 60000)],
        '6****': [f"{i:05d}" for i in range(60000, 70000)],
        '7****': [f"{i:05d}" for i in range(70000, 80000)],
        '8****': [f"{i:05d}" for i in range(80000, 90000)],
        '9****': [f"{i:05d}" for i in range(90000, 100000)]
    }
    levels.append({
        'level': 4,
        'description': 'Broad region (first digit only)',
        'mapping': level4_mapping
    })
    
    return {
        'attribute_type': 'zipcode',
        'description': 'Zip code hierarchy: exact -> prefix -> area -> region -> suppressed',
        'levels': levels
    }


def get_occupation_hierarchy_template() -> Dict:
    """
    Occupation/Job category hierarchy.
    
    Levels:
    0: Exact job title
    1: Job category
    2: Industry sector
    3: Broad sector
    4: Suppressed
    """
    levels = []
    
    # Level 0 is implicit (identity)
    levels.append({
        'level': 0,
        'description': 'Exact occupation',
        'mapping': {}
    })
    
    # Level 1: Job categories
    level1_mapping = {
        'Healthcare': ['Doctor', 'Nurse', 'Surgeon', 'Dentist', 'Pharmacist', 'Therapist', 
                       'Medical Technician', 'Healthcare Administrator', 'Paramedic'],
        'Technology': ['Software Engineer', 'Data Scientist', 'IT Specialist', 'Web Developer',
                       'System Administrator', 'Network Engineer', 'Database Administrator',
                       'Security Analyst', 'DevOps Engineer', 'AI Engineer'],
        'Education': ['Teacher', 'Professor', 'Lecturer', 'Principal', 'School Counselor',
                      'Tutor', 'Education Administrator', 'Trainer'],
        'Business': ['Accountant', 'Financial Analyst', 'Marketing Manager', 'Business Analyst',
                     'HR Manager', 'Project Manager', 'Operations Manager', 'CEO', 'CFO'],
        'Engineering': ['Civil Engineer', 'Mechanical Engineer', 'Electrical Engineer',
                        'Chemical Engineer', 'Structural Engineer', 'Environmental Engineer'],
        'Arts': ['Artist', 'Designer', 'Writer', 'Photographer', 'Musician', 'Actor'],
        'Services': ['Chef', 'Bartender', 'Waiter', 'Receptionist', 'Security Guard',
                     'Cleaner', 'Driver', 'Retail Worker'],
        'Agriculture': ['Farmer', 'Agricultural Technician', 'Forestry Worker', 'Fisher'],
        'Manufacturing': ['Machine Operator', 'Factory Worker', 'Quality Control', 'Supervisor'],
        'Other': ['Unemployed', 'Student', 'Retired', 'Other']
    }
    levels.append({
        'level': 1,
        'description': 'Job category',
        'mapping': level1_mapping
    })
    
    # Level 2: Industry sectors
    level2_mapping = {
        'Healthcare & Social': level1_mapping['Healthcare'],
        'Information Technology': level1_mapping['Technology'],
        'Education': level1_mapping['Education'],
        'Finance & Business': level1_mapping['Business'] + level1_mapping['Engineering'],
        'Arts & Media': level1_mapping['Arts'],
        'Services': level1_mapping['Services'],
        'Primary Sector': level1_mapping['Agriculture'],
        'Manufacturing': level1_mapping['Manufacturing'],
        'Other': level1_mapping['Other']
    }
    levels.append({
        'level': 2,
        'description': 'Industry sector',
        'mapping': level2_mapping
    })
    
    # Level 3: Broad sectors
    level3_mapping = {
        'White Collar': level2_mapping['Information Technology'] + level2_mapping['Education'] + 
                         level2_mapping['Finance & Business'],
        'Blue Collar': level2_mapping['Services'] + level2_mapping['Manufacturing'] + 
                       level2_mapping['Primary Sector'],
        'Healthcare': level2_mapping['Healthcare & Social'],
        'Other': level2_mapping['Arts & Media'] + level2_mapping['Other']
    }
    levels.append({
        'level': 3,
        'description': 'Broad sector',
        'mapping': level3_mapping
    })
    
    # Level 4: Complete suppression
    all_occupations = []
    for cats in level1_mapping.values():
        all_occupations.extend(cats)
    levels.append({
        'level': 4,
        'description': 'Worker (no specific occupation)',
        'mapping': {'Worker': all_occupations}
    })
    
    return {
        'attribute_type': 'occupation',
        'description': 'Occupation hierarchy: Job -> Category -> Industry -> Sector',
        'levels': levels
    }


def get_education_hierarchy_template() -> Dict:
    """
    Education level hierarchy.
    
    Levels:
    0: Exact degree
    1: Education level
    2: Broad level
    3: Suppressed
    """
    levels = []
    
    # Level 0 is implicit (identity)
    levels.append({
        'level': 0,
        'description': 'Exact degree',
        'mapping': {}
    })
    
    # Level 1: Education levels
    level1_mapping = {
        'Primary': ['Primary School', 'No Formal Education'],
        'Secondary': ['O-Level', 'High School Diploma', 'GCSE'],
        'Diploma': ['Certificate', 'Diploma', 'Advanced Diploma'],
        'Bachelor': ['Bachelor Degree', 'BSc', 'BA', 'BCom', 'BEng'],
        'Master': ['Master Degree', 'MSc', 'MA', 'MBA', 'MEng'],
        'Doctorate': ['PhD', 'Doctorate', 'MD']
    }
    levels.append({
        'level': 1,
        'description': 'Education level',
        'mapping': level1_mapping
    })
    
    # Level 2: Broad categories
    level2_mapping = {
        'Below Tertiary': level1_mapping['Primary'] + level1_mapping['Secondary'],
        'Tertiary': level1_mapping['Diploma'] + level1_mapping['Bachelor'],
        'Postgraduate': level1_mapping['Master'] + level1_mapping['Doctorate']
    }
    levels.append({
        'level': 2,
        'description': 'Broad education category',
        'mapping': level2_mapping
    })
    
    # Level 3: Complete suppression
    all_edu = []
    for cats in level1_mapping.values():
        all_edu.extend(cats)
    levels.append({
        'level': 3,
        'description': 'Educated (no specific level)',
        'mapping': {'Educated': all_edu}
    })
    
    return {
        'attribute_type': 'education',
        'description': 'Education hierarchy: Degree -> Level -> Category',
        'levels': levels
    }


def get_gender_hierarchy_template() -> Dict:
    """
    Gender hierarchy (minimal - usually not generalized).
    """
    levels = []
    
    # Level 0: Exact value
    levels.append({
        'level': 0,
        'description': 'Exact gender',
        'mapping': {}
    })
    
    # Level 1: Grouped (rarely used)
    level1_mapping = {
        'Male': ['Male', 'M', 'm'],
        'Female': ['Female', 'F', 'f'],
        'Other': ['Other', 'Non-binary', 'Prefer not to say']
    }
    levels.append({
        'level': 1,
        'description': 'Grouped gender',
        'mapping': level1_mapping
    })
    
    # Level 2: Person (very broad)
    levels.append({
        'level': 2,
        'description': 'Person (no gender specified)',
        'mapping': {'Person': ['Male', 'Female', 'Other', 'M', 'F', 'm', 'f', 'Non-binary', 'Prefer not to say']}
    })
    
    return {
        'attribute_type': 'gender',
        'description': 'Gender hierarchy (minimal)',
        'levels': levels
    }


def get_default_templates() -> Dict[str, Dict]:
    """
    Get all default hierarchy templates.
    
    Returns:
        Dict mapping attribute types to their hierarchy templates
    """
    return {
        'age': get_age_hierarchy_template(),
        'geography': get_geography_hierarchy_template(),
        'date': get_date_hierarchy_template(),
        'zipcode': get_zipcode_hierarchy_template(),
        'occupation': get_occupation_hierarchy_template(),
        'education': get_education_hierarchy_template(),
        'gender': get_gender_hierarchy_template()
    }


def detect_attribute_type(column_name: str, sample_values: List[Any] = None) -> str:
    """
    Detect the likely type of an attribute based on its name and sample values.
    
    IMPORTANT: Column name takes precedence over numeric dtype because many
    categorical attributes (especially in census data) use numeric codes.
    
    Args:
        column_name: Name of the column
        sample_values: Optional sample values to help with detection
        
    Returns:
        Detected attribute type (key from get_default_templates)
    """
    name_lower = column_name.lower()
    
    # IMPORTANT: Check column name FIRST, before checking numeric dtype
    # This is because census/survey data often uses numeric codes for categorical variables
    # e.g., province=1,2,3... or sex=1,2 or education_level=1,2,3...
    
    # Check by name patterns first (highest priority)
    if any(kw in name_lower for kw in ['age', 'age_years', 'ageyears']):
        return 'age'
    elif any(kw in name_lower for kw in [
        'location', 'address', 'city', 'district', 'province', 'region', 'country', 'geography',
        # Sri Lanka census/admin terminology
        'ds_', 'dsd', 'divisional', 'secretariat', 'gn', 'grama', 'niladhari', 'ea', 'enumeration',
        'sector'  # In Sri Lanka census, sector = urban/rural
    ]):
        return 'geography'
    elif any(kw in name_lower for kw in ['zip', 'postal', 'zipcode', 'postcode']):
        return 'zipcode'
    elif any(kw in name_lower for kw in ['date', 'dob', 'birth_date', 'birthday', 'year', 'datetime']):
        return 'date'
    elif any(kw in name_lower for kw in ['income', 'salary', 'wage', 'pay', 'earnings', 'lkr', 'rs', 'rupees']):
        return 'income'
    elif any(kw in name_lower for kw in ['job', 'occupation', 'profession', 'work', 'employment', 'title', 'position', 'role']):
        return 'occupation'
    elif any(kw in name_lower for kw in [
        'education', 'degree', 'qualification', 'school', 'university', 'college',
        # Sri Lanka common education labels
        'ol', 'o_level', 'al', 'a_level', 'gce'
    ]):
        return 'education'
    elif any(kw in name_lower for kw in ['gender', 'sex', 'male', 'female']):
        return 'gender'
    
    # If sample values provided, try to detect from values
    # But STILL respect the column name semantics - don't treat numeric codes as age/income
    if sample_values:
        # First check if this looks like a categorical coded variable
        unique_ratio = len(set(sample_values)) / len(sample_values) if sample_values else 0
        
        # If low unique ratio (< 50%), it's likely categorical even if numeric codes
        if unique_ratio < 0.5:
            # Could be categorical codes - try to infer from value ranges
            try:
                numeric_vals = [float(v) for v in sample_values if v is not None]
                if numeric_vals:
                    min_val = min(numeric_vals)
                    max_val = max(numeric_vals)
                    
                    # Check for typical categorical code ranges
                    # Sex/Gender codes: 1,2 (sometimes 1=Male, 2=Female)
                    if max_val <= 2:
                        return 'gender'
                    # Education levels: typically 1-10 or so
                    elif max_val <= 15 and min_val >= 0:
                        return 'education'
                    # Ethnicity codes: typically small range
                    elif max_val <= 10:
                        return 'categorical'
                    # Religion codes: typically small range
                    # Marital status: typically 1-5
                    elif max_val <= 6:
                        return 'categorical'
            except (ValueError, TypeError):
                pass
        
        # Check if numeric (could be age or income) - but only if not a clear code
        try:
            numeric_vals = [float(v) for v in sample_values if v is not None]
            if numeric_vals:
                avg = sum(numeric_vals) / len(numeric_vals)
                min_val = min(numeric_vals)
                max_val = max(numeric_vals)
                
                # Age: typically 0-120 for people
                if 0 <= min_val <= 120 and 0 <= avg <= 120 and max_val <= 120:
                    return 'age'
                # Income: typically > 1000 (in LKR or other currency)
                elif min_val > 100:
                    return 'income'
        except (ValueError, TypeError):
            pass
    
    # Default to categorical
    return 'categorical'


def get_hierarchy_for_attribute(
    column_name: str,
    sample_values: List[Any] = None,
    custom_mappings: Dict[str, Dict] = None
) -> Optional[Dict]:
    """
    Get an appropriate hierarchy template for an attribute.
    
    Args:
        column_name: Name of the column
        sample_values: Optional sample values
        custom_mappings: Optional custom hierarchy mappings
        
    Returns:
        Hierarchy template dict, or None if no suitable template
    """
    attr_type = detect_attribute_type(column_name, sample_values)
    
    templates = get_default_templates()
    
    if attr_type in templates:
        return templates[attr_type]
    
    return None
