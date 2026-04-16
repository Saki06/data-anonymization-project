"""
Configuration constants for the HIES column-classification pipeline.

Ported from hies/src/config.py
"""

import re

# ---------------------------------------------------------------------------
# Direct identifier constants
# ---------------------------------------------------------------------------

HIGH_PRIORITY_DIRECT_IDENTIFIERS = [
    'district', 'psu', 'snumber', 'hhno', 'person_serial_no',
    'person_serial_number', 'household_number', 'household_no',
]

DIRECT_IDENTIFIER_KEYWORDS = {
    'id':       ['id', 'identifier', 'uuid', 'guid', 'ssn', 'social security'],
    'name':     ['name', 'firstname', 'lastname', 'fullname', 'surname', 'given name'],
    'email':    ['email', 'e-mail', 'mail'],
    'phone':    ['phone', 'telephone', 'mobile', 'cell', 'contact'],
    'address':  ['address', 'street', 'postal', 'zip', 'postcode'],
    'ip':       ['ip', 'ip address', 'ipaddress'],
    'mac':      ['mac address', 'macaddress'],
    'passport': ['passport', 'passport number', 'passportno'],
    'license':  ['license', 'driving license', 'license number', 'licenseno'],
    'account':  ['account', 'account number', 'accountno', 'bank account'],
}

DIRECT_IDENTIFIER_PATTERNS = {
    'ssn':   re.compile(r'\b\d{3}-?\d{2}-?\d{4}\b'),
    'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    'phone': re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|\b\(\d{3}\)\s?\d{3}[-.]?\d{4}\b'),
    'ip':    re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
    'uuid':  re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I),
}

# ---------------------------------------------------------------------------
# Quasi-identifier constants
# ---------------------------------------------------------------------------

HIGH_PRIORITY_QUASI_IDENTIFIERS = [
    'age', 'sex', 'education', 'marital_status', 'maritalstatus',
    'occupation', 'industry', 'sector', 'residence', 'residence_type',
    'urban_rural', 'urbanrural', 'rural_urban',
]

QUASI_IDENTIFIER_KEYWORDS = {
    'age':         ['age', 'dob', 'date of birth', 'birthdate', 'birth date', 'year of birth', 'yob'],
    'gender':      ['gender', 'sex', 'male', 'female'],
    'location':    ['location', 'city', 'town', 'village', 'ward', 'region', 'province', 'state', 'county'],
    'education':   ['education', 'edu', 'qualification', 'degree', 'school', 'university'],
    'occupation':  ['occupation', 'job', 'profession', 'employment', 'work'],
    'marital':     ['marital', 'marriage', 'married', 'single', 'divorced', 'widowed'],
    'industry':    ['industry', 'sector', 'economic sector'],
    'residence':   ['residence', 'residence_type', 'urban', 'rural', 'urban_rural'],
    'race':        ['race', 'ethnicity', 'ethnic'],
    'language':    ['language', 'lang', 'mother tongue'],
    'postcode':    ['postcode', 'postal code', 'zip code', 'zip'],
    'coordinates': ['latitude', 'longitude', 'lat', 'lon', 'coord'],
}

# ---------------------------------------------------------------------------
# Sensitive attribute constants
# ---------------------------------------------------------------------------

HIGH_PRIORITY_SENSITIVE = [
    'religion', 'ethnicity', 'ethnic',
]

SENSITIVE_KEYWORDS = {
    'health':    ['health', 'medical', 'disease', 'illness', 'diagnosis', 'treatment', 'hospital', 'clinic', 'disability'],
    'income':    ['income', 'salary', 'wage', 'earnings', 'revenue', 'pay'],
    'financial': ['financial', 'bank', 'credit', 'debt', 'loan', 'mortgage', 'asset', 'wealth'],
    'religion':  ['religion', 'religious', 'faith', 'belief', 'denomination'],
    'ethnicity': ['ethnicity', 'ethnic', 'race', 'tribal', 'caste'],
    'political': ['political', 'party', 'vote', 'voting', 'election'],
    'sexual':    ['sexual', 'orientation', 'lgbt', 'lgbtq'],
    'criminal':  ['criminal', 'crime', 'arrest', 'conviction', 'felony', 'misdemeanor'],
    'genetic':   ['genetic', 'dna', 'genome', 'biometric'],
}

# ---------------------------------------------------------------------------
# Column normalisation patterns
# ---------------------------------------------------------------------------

COLUMN_NORMALIZE_PATTERNS = [
    (re.compile(r'[_\s]+'), '_'),
    (re.compile(r'[^\w\s]'), ''),
    (re.compile(r'^_+|_+$'), ''),
]

# ---------------------------------------------------------------------------
# Confidence & risk thresholds
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLDS = {'high': 0.8, 'medium': 0.5, 'low': 0.3}

RISK_THRESHOLDS = {
    'high_risk_k':      2,
    'medium_risk_k':    5,
    'unique_threshold': 0.1,
}
