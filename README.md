# 🛡️ Data Anonymization Platform

An AI-driven, end-to-end platform for automating the anonymization of sensitive datasets — from intelligent data profiling and expert-guided anonymization to multi-objective optimization, synthetic data generation, and re-identification risk assessment.

> Built as an academic research project at **SLIIT** (Sri Lanka Institute of Information Technology).

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Research Components](#research-components)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [API Endpoints](#api-endpoints)
- [Team](#team)

---

## Overview

Organizations handling personal data face increasing regulatory pressure (GDPR, HIPAA, POPIA) to protect individual privacy before sharing or analyzing datasets. Manual anonymization is error-prone, inconsistent, and fails to balance **privacy** with **data utility**.

This platform automates the entire anonymization lifecycle:

1. **Upload & Profile** — Inspect and validate raw datasets
2. **Identify & Classify** — Detect direct identifiers, quasi-identifiers, and sensitive attributes
3. **Anonymize** — Apply SDC techniques with hierarchy-aware generalization
4. **Optimize** — Use NSGA-II to find Pareto-optimal privacy–utility trade-offs
5. **Generate Synthetic Data** — Create privacy-preserving synthetic alternatives
6. **Assess Risk** — Simulate ML-based re-identification attacks and score residual risk
7. **Explain** — Generate natural-language risk reports using LLMs

---

## Key Features

| Module | Description |
|--------|-------------|
| 🔐 **Authentication** | JWT-based auth with signup/login and MongoDB user store |
| 📤 **Data Upload** | CSV file ingestion with schema validation and data profiling |
| 🏷️ **Quasi-Identifier Selection** | Automatic detection of direct IDs, QIs, and sensitive attributes |
| 🔒 **Anonymization Engine** | k-Anonymity, generalization, suppression, perturbation, PRAM, and more |
| 🧠 **Expert System** | Rule-based knowledge base with recommendation engine for optimal anonymization strategies |
| ⚙️ **Pipeline Generator** | Auto-generate and validate complete anonymization pipelines |
| 📊 **NSGA-II Optimization** | Multi-objective evolutionary optimization balancing privacy vs. utility |
| 🧬 **Synthetic Data Generation** | Generate synthetic datasets with statistical utility evaluation |
| 🔬 **Re-Identification Risk Assessment** | 7-agent ML pipeline simulating linkage attacks with SHAP explainability |
| 🤖 **LLM Risk Explainer** | GPT-4o-mini powered natural language risk reporting |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js + React)               │
│   Dashboard │ Upload │ QI Selection │ Anonymize │ Risk View │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API
┌──────────────────────────▼──────────────────────────────────┐
│                    Backend (FastAPI + Python)               │
│                                                             │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │  Upload   │ │ QI Selection │ │   Anonymization Engine  │ │
│  └──────────┘ └──────────────┘ │ • k-Anonymity            │ │
│                                │ • Generalization         │ │
│  ┌──────────────────────────┐  │ • Suppression            │ │
│  │     Expert System        │  │ • Perturbation / PRAM    │ │
│  │ • Knowledge Base         │  └──────────────────────────┘ │
│  │ • Rules Engine           │                               │
│  │ • Recommendation Engine  │  ┌──────────────────────────┐ │
│  │ • Pipeline Generator     │  │  NSGA-II Optimizer       │ │
│  └──────────────────────────┘  │  (Privacy vs. Utility)   │ │
│                                └──────────────────────────┘ │
│  ┌──────────────────────────┐  ┌──────────────────────────┐ │
│  │  Synthetic Data Module   │  │  Re-Identification Risk  │ │
│  │ • APEDP Generator        │  │  Assessment (7 Agents)   │ │
│  │ • Utility Metrics        │  │ • ML Attack Simulation   │ │
│  └──────────────────────────┘  │ • SHAP Explainability    │ │
│                                │ • LLM Risk Reporting     │ │
│                                └──────────────────────────┘ │
│  ┌──────────┐                                               │
│  │   Auth   │ ◄── MongoDB (User Store)                      │
│  │  (JWT)   │                                               │
│  └──────────┘                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | Next.js 16, React 18, TypeScript, Tailwind CSS, Lucide Icons |
| **Backend** | FastAPI, Uvicorn, Python 3.10+ |
| **ML / AI** | scikit-learn, XGBoost, SHAP, NSGA-II |
| **NLP** | OpenAI GPT-4o-mini |
| **Database** | MongoDB (via Motor async driver) |
| **Auth** | JWT (python-jose), bcrypt (passlib) |
| **Data** | Pandas, NumPy, SciPy, Matplotlib |

---

## Research Components

### 1. Expert System for Anonymization Recommendations

An AI-driven expert system that combines a **knowledge base**, **rules engine**, and **recommendation engine** to suggest optimal anonymization strategies based on dataset characteristics and regulatory requirements.

### 2. NSGA-II Multi-Objective Optimization

Applies the **Non-dominated Sorting Genetic Algorithm II** to find Pareto-optimal configurations that balance:
- **Privacy** (minimizing re-identification risk)
- **Utility** (preserving statistical properties of the data)

### 3. Synthetic Data Generation & Evaluation

Generates privacy-preserving synthetic datasets and evaluates their quality using utility metrics such as propensity scores and statistical similarity measures.

### 4. Re-Identification Risk Assessment (7-Agent Pipeline)

A sequential multi-agent pipeline that simulates real-world linkage attacks:

| Agent | Role | Key Technique |
|-------|------|---------------|
| Agent 1 | **Data Inspector** | Schema validation, profiling, anomaly detection |
| Agent 2 | **Identifier Manager** | QI validation, column mapping, value-overlap suggestions |
| Agent 3 | **Pair Generator** | Dynamic blocking, feature engineering, train/test split |
| Agent 4 | **ML Attacker** | Logistic Regression, Random Forest, GBM, XGBoost |
| Agent 5 | **Risk Scorer** | Attack probability scoring, SHAP explainability, k-anonymity & LOF analysis |
| Agent 6 | **Risk Aggregator** | Weighted fusion (50% ML + 30% Internal + 20% Uniqueness) |
| Agent 7 | **LLM Explainer** | GPT-4o-mini natural language risk explanations |

---

## Project Structure

```
Data_Anonymization_SLIIT/
├── backend/
│   ├── main.py                          # FastAPI entry point
│   └── components/
│       ├── auth/                        # JWT authentication + MongoDB
│       ├── upload/                      # CSV upload & session management
│       ├── quasi_selection/             # QI / DI / SA detection
│       ├── anonymization/              # Anonymization methods + hierarchy
│       ├── expert_system/              # Knowledge base + rules + recommendations
│       ├── optimization/               # NSGA-II optimizer
│       ├── synthetic_data/             # Synthetic data generation
│       ├── ai_agent/                   # Risk analyzer agent
│       └── reidentification/           # 7-agent risk assessment pipeline
│           
├── frontend-nextjs/
│   ├── app/
│   │   ├── login/                      # Login page
│   │   ├── signup/                     # Signup page
│   │   ├── dashboard/                  # Main dashboard
│   │   ├── quasi-selection/            # QI selection UI
│   │   ├── anonymization/             # Anonymization controls
│   │   ├── pipeline-generation/       # Pipeline builder
│   │   ├── solution-selection/        # Solution comparison
│   │   ├── synthetic-data/            # Synthetic data module
│   │   └── reidentification/          # Risk assessment dashboard
│   └── components/                     # Shared UI components
├── requirements.txt                    # Python dependencies
└── .env                                # Environment variables
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB instance (local or Atlas)
- OpenAI API key (for Agent 7 LLM explanations)

### 1. Clone the Repository

```bash
git clone https://github.com/Saki06/data-anonymization-project.git
cd data-anonymization-project
```

### 2. Backend Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key
MONGODB_URL=mongodb://localhost:27017
JWT_SECRET_KEY=your_jwt_secret
```

### 4. Start the Backend

```bash
cd backend
python main.py
```

The API will be available at `http://localhost:8000`.

### 5. Frontend Setup

```bash
cd frontend-nextjs
npm install
npm run dev
```

The UI will be available at `http://localhost:3000`.

---

## API Endpoints

| Prefix | Module | Description |
|--------|--------|-------------|
| `/auth` | Authentication | Signup, login, JWT token management |
| `/upload` | Data Upload | CSV file upload and session creation |
| `/quasi` | QI Selection | Identifier classification and detection |
| `/anonymization` | Anonymization | Apply SDC methods with hierarchy support |
| `/expert` | Expert System | Get anonymization recommendations |
| `/synthetic` | Synthetic Data | Generate and evaluate synthetic datasets |
| `/reid` | Re-Identification | Full 7-agent risk assessment pipeline |

---

## Team

| Member | Research Component |
|--------|--------------------|
| Member 1 | Expert System & Anonymization Recommendations |
| Member 2 | NSGA-II Multi-Objective Optimization |
| Member 3 | Synthetic Data Generation & Evaluation |
| Member 4 | Re-Identification Risk Assessment (7-Agent Pipeline) |

---

<p align="center">
  Built with ❤️ at <strong>SLIIT</strong> — Sri Lanka Institute of Information Technology
</p>
