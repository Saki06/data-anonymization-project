"""
Prompt templates for LLM-based natural language explanations
"""

# System prompt to guide LLM behavior
SYSTEM_PROMPT = """
You are a privacy risk assistant.
Write short, plain English explanations for non-technical readers.
Maximum 200 words per explanation.
Use simple language. Short sentences only.
Never use technical terms like SHAP, feature vector, cosine similarity, or euclidean distance.
Use original column names exactly as given. Do not rename them.
Always end with the mandatory disclaimer exactly as given.
Never say the record is re-identified or the person is exposed.
"""

# Prompt for explaining individual record risk
RECORD_EXPLANATION_PROMPT = """
Explain this privacy risk result in plain English.

Risk score: {risk_score:.4f} (0.0 = no risk, 1.0 = highest risk)

Columns that contributed most to this risk:
{shap_features}

Rules:
- Write exactly 3 paragraphs.
- Under 180 words total.
- Simple language. Short sentences only.
- Paragraph 1: What the risk score means for this record. Describe how high or low it is.
- Paragraph 2: Which columns drove the risk most. Explain why each matters in simple terms.
- Paragraph 3: Which columns need better anonymization and what kind of changes could help.
- Use the column names exactly as listed above. Do not rename them.
- Do NOT use words like SHAP, feature, vector, cosine, or euclidean.
- Do not say the record is re-identified.
- End with this exact line:
  "Risk scores represent ML model confidence under simulated attack conditions, not real-world re-identification probability."
"""

# Prompt for dataset-level summary
DATASET_SUMMARY_PROMPT = """
Summarize this dataset's privacy risk in plain English.

Total records: {total_records}
Average risk score: {avg_risk:.4f}
High risk records: {high_risk_count} ({high_risk_pct:.1f}%)
Medium risk records: {medium_risk_count} ({medium_risk_pct:.1f}%)
Low risk records: {low_risk_count} ({low_risk_pct:.1f}%)

Columns that matter most for risk:
{global_shap_features}

Rules:
- Write exactly 3 paragraphs.
- Under 230 words total.
- Plain English only. Short sentences only.
- Paragraph 1: Describe the overall risk score distribution in simple terms. Mention what the high/medium/low counts mean for the dataset.
- Paragraph 2: Name the top columns using their exact names. Explain why each one matters and how combining them increases risk.
- Paragraph 3: Say which columns need stronger anonymization. Suggest specific steps such as grouping ages, broadening categories, or removing rare values.
- Use column names exactly as listed above. Do not rename them.
- Do NOT use words like SHAP, feature vector, cosine, or euclidean.
- End with this exact disclaimer:
  "Risk scores represent ML model confidence under simulated attack conditions, not real-world re-identification probability."
"""

# Prompt for comparative analysis (high vs low risk)
COMPARATIVE_PROMPT = """
Compare high-risk and low-risk records in plain English.

High-risk group:
{high_risk_profile}

Low-risk group:
{low_risk_profile}

Rules:
- Write exactly 2 short paragraphs.
- Under 100 words total.
- Plain English only. Short sentences only.
- Use original column names exactly as shown above. Do not rename them.
- Do NOT use words like SHAP, feature vector, cosine, or euclidean.
- Do not say any record is re-identified.
- No disclaimer needed here.
"""

# Prompt for feature-specific explanation
FEATURE_EXPLANATION_PROMPT = """Explain the SHAP importance of '{feature_name}' in the ML attack model:

**Feature Statistics:**
{feature_stats}

**SHAP Importance Score:** {shap_importance:.4f}

**Task:**
In 1-2 paragraphs, explain:
1. What this SHAP importance score indicates about the model's reliance on this feature
2. How the model uses this feature in its matching predictions (based on SHAP analysis)
3. Whether this column may be considered for enhanced anonymization based on its SHAP contribution

REQUIRED FRAMING:
- Use "the model relies on this feature" NOT "this feature enables re-identification"
- Use "SHAP analysis indicates" NOT causal statements
- Use "may be considered for" NOT "requires" when suggesting mitigations

Be precise and analytically grounded in SHAP interpretability.
"""
