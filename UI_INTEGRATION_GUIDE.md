# UI Integration Guide - Pipeline Generation & Solution Selection

## Overview

This guide explains how the new UI pages (Pipeline Generation and Solution Selection) integrate with the backend API.

---

## Pages Created

### 1. **Pipeline Generation Page** (`/pipeline-generation`)
- **Location**: `frontend-nextjs/app/pipeline-generation/page.tsx`
- **Purpose**: Displays generated pipelines and their details
- **Features**:
  - Shows all generated pipelines with expandable details
  - Displays pipeline type (single-method, hybrid, rule-based)
  - Shows privacy targets (k, l, t values)
  - Displays expected utility impact
  - Summary statistics (total pipelines, single vs hybrid count)
  - Button to proceed to optimization

### 2. **Solution Selection Page** (`/solution-selection`)
- **Location**: `frontend-nextjs/app/solution-selection/page.tsx`
- **Purpose**: Displays Pareto front solutions and enables selection
- **Features**:
  - Shows recommended solution (best trade-off)
  - Displays all Pareto front solutions with metrics
  - Auto-select mode (automatic selection)
  - Human-in-loop mode (user selects from top 5)
  - Visual metrics: privacy score, utility score, distance to ideal
  - Expandable solution details
  - Optimization metrics display

### 3. **Pareto Front Visualization** (`components/ParetoFrontVisualization.tsx`)
- **Purpose**: Renders interactive Pareto front chart
- **Features**:
  - X-axis: Privacy Score
  - Y-axis: Utility Score
  - Points represent solutions
  - Ideal point marked at (0,0)
  - Click-to-select functionality
  - Pareto front line visualization

---

## Backend API Endpoints Required

### Endpoint 1: Generate Pipelines
```
POST /anonymization/generate-pipelines
```

**Request Body**:
```json
{
  "session_id": "string",
  "num_pipelines": 20,
  "quasi_identifiers": ["col1", "col2"],
  "sensitive_attributes": ["col3"]
}
```

**Response**:
```json
{
  "pipelines": [
    {
      "pipeline_id": 1,
      "steps": [
        {
          "method": "k-anonymity",
          "target_columns": ["age", "gender"],
          "parameters": {"k": 5}
        }
      ],
      "privacy_target": {"k": 5, "l": 2, "t": 0.2},
      "privacy_level": "High",
      "utility_impact": "Medium",
      "description": "k-anonymity on quasi-identifiers"
    }
  ]
}
```

### Endpoint 2: Optimize Pipelines (NSGA-II)
```
POST /anonymization/optimize-pipelines
```

**Request Body**:
```json
{
  "session_id": "string",
  "pipelines": [
    {
      "pipeline_id": 1,
      "steps": [...],
      "privacy_target": {...},
      "privacy_level": "High",
      "utility_impact": "Medium",
      "description": "..."
    }
  ]
}
```

**Response**:
```json
{
  "pareto_front": [
    {
      "pipeline_id": 2,
      "privacy_score": 0.25,
      "utility_score": 0.15,
      "distance_to_ideal": 0.27,
      "rank": 1,
      "k_value": 5,
      "l_value": 2,
      "t_value": 0.15,
      "pipeline_description": "k-anonymity + l-diversity"
    }
  ],
  "total_pipelines_evaluated": 20,
  "best_solution": {...},
  "optimization_metrics": {
    "privacy_improvement": 0.85,
    "utility_preservation": 0.78
  }
}
```

### Endpoint 3: Get Pareto Front
```
POST /anonymization/get-pareto-front
```

**Request Body**:
```json
{
  "session_id": "string"
}
```

**Response**:
```json
{
  "pareto_front": [...],
  "total_pipelines_evaluated": 20,
  "best_solution": {...},
  "optimization_metrics": {...}
}
```

### Endpoint 4: Select Solution
```
POST /anonymization/select-solution
```

**Request Body**:
```json
{
  "session_id": "string",
  "pipeline_id": 2,
  "mode": "auto" | "human"
}
```

**Response**:
```json
{
  "selected_pipeline_id": 2,
  "selection_mode": "auto",
  "selection_rationale": {
    "privacy_score": 0.25,
    "utility_score": 0.15,
    "distance_to_ideal": 0.27,
    "reason": "Best overall trade-off among all solutions"
  }
}
```

---

## Integration with Anonymization Flow

### Current Flow
1. **Upload** → `POST /upload/upload-csv`
2. **Quasi-Selection** → `POST /anonymization/detect-qi`
3. **Risk Analysis** → `POST /anonymization/analyze-risk`
4. **Recommendations** → Returns best methods (Agent 4)
5. **[NEW] Pipeline Generation** → `POST /anonymization/generate-pipelines` (Agent 5)
6. **[NEW] Solution Selection** → `POST /anonymization/optimize-pipelines` (Agents 6-7)
7. **Execute** → `POST /anonymization/execute`
8. **Validate** → Post-validation (Agent 9)

### Routing Integration

Update `anonymization/page.tsx` to include steps for pipeline generation and solution selection:

```typescript
const steps = [
  { number: 1, title: 'Upload Data', path: '/anonymization' },
  { number: 2, title: 'Select QIDs', path: '/quasi-selection' },
  { number: 3, title: 'Risk Analysis', path: '/anonymization?step=analysis' },
  { number: 4, title: 'Generate Pipelines', path: '/pipeline-generation' },  // NEW
  { number: 5, title: 'Select Solution', path: '/solution-selection' },      // NEW
  { number: 6, title: 'Execute', path: '/anonymization?step=execute' },
  { number: 7, title: 'Validate', path: '/anonymization?step=validate' },
];
```

---

## Session Context Usage

Both pages use `SessionContext` to manage:
- `sessionId`: Unique session identifier
- `API_BASE`: Base URL for API calls
- Data persistence across pages

### Example Usage:
```typescript
const { sessionId, API_BASE: apiBaseUrl } = useSession();
```

---

## State Management

### Pipeline Generation Page State
```typescript
interface GenerationState {
  loading: boolean;
  success: boolean;
  error: string | null;
  pipelines: AnonymizationPipeline[];
  selectedPipeline: number | null;
}
```

### Solution Selection Page State
```typescript
interface SelectionState {
  loading: boolean;
  success: boolean;
  error: string | null;
  results: OptimizationResult | null;
  selectedMode: 'auto' | 'human';
  userSelectedId: number | null;
  expandedSolution: number | null;
  executing: boolean;
}
```

---

## Component Dependencies

### Imports Used
- **lucide-react**: Icons for UI elements
  - `ChevronDown`, `ChevronUp`, `Zap`, `TrendingUp`, `TrendingDown`, `AlertCircle`, `CheckCircle`, `BarChart3`, `Target`
- **next/navigation**: Routing and navigation
- **SessionContext**: Session management
- **Breadcrumb**, **StatusBadge**, **DataTable**: Reusable components

---

## Styling

All pages use **Tailwind CSS** with:
- Light/Dark theme support
- Responsive grid layouts
- Gradient backgrounds
- Hover effects and transitions
- Badge/chip components for status
- Card-based layout

---

## Error Handling

Both pages include:
- API error messages displayed to users
- Loading states with visual feedback
- Success confirmation messages
- Graceful fallbacks for missing data
- Session validation

---

## Next Steps for Backend Integration

1. **Implement API Endpoints**:
   - Create `/anonymization/generate-pipelines` endpoint in `backend/components/anonymization/routes.py`
   - Create `/anonymization/optimize-pipelines` endpoint
   - Create `/anonymization/get-pareto-front` endpoint
   - Create `/anonymization/select-solution` endpoint

2. **Connect to Agents**:
   - Agent 5 (Pipeline Generator): Call in `/generate-pipelines` endpoint
   - Agent 6 (NSGA-II): Call in `/optimize-pipelines` endpoint
   - Agent 7 (Decision): Call in `/select-solution` endpoint

3. **Session Storage**:
   - Store generated pipelines in session
   - Store optimization results in session
   - Retrieve in subsequent requests

4. **Testing**:
   - Test pipeline generation with various datasets
   - Test NSGA-II optimization with generated pipelines
   - Test solution selection in both modes
   - Verify data consistency across pages

---

## Example API Implementation

### Route: `/anonymization/generate-pipelines`
```python
from fastapi import APIRouter, Depends, HTTPException
from backend.components.expert_system.knowledge_base import AnonymizationKnowledgeBase

router = APIRouter()
kb = AnonymizationKnowledgeBase()

@router.post("/generate-pipelines")
async def generate_pipelines(request: dict):
    session_id = request.get("session_id")
    num_pipelines = request.get("num_pipelines", 20)
    
    # Load risk profile from session
    risk_profile = load_from_session(session_id, "risk_profile")
    
    # Get recommendations from Agent 4
    recommendations = kb.recommend_methods(risk_profile)
    
    # Generate pipelines from Agent 5
    pipelines = kb.generate_anonymization_pipelines(
        recommendations=recommendations,
        num_pipelines=num_pipelines
    )
    
    # Store in session
    save_to_session(session_id, "pipelines", pipelines)
    
    return {
        "pipelines": [p.to_dict() for p in pipelines],
        "total": len(pipelines)
    }
```

---

## Deployment Checklist

- [ ] Create all 4 API endpoints
- [ ] Connect to Agent 5, 6, 7
- [ ] Test pipeline generation
- [ ] Test NSGA-II optimization
- [ ] Test solution selection
- [ ] Verify session persistence
- [ ] Test error handling
- [ ] Deploy frontend pages
- [ ] Update navigation in sidebar
- [ ] Test end-to-end flow

---

## Troubleshooting

**Issue**: Pages not loading  
**Solution**: Check session is initialized, verify API base URL

**Issue**: Pipelines not displayed  
**Solution**: Check API endpoint returns correct format, verify session storage

**Issue**: Pareto front empty  
**Solution**: Verify NSGA-II optimization runs, check pipeline evaluation

**Issue**: Solution selection fails  
**Solution**: Verify pipeline selection is stored, check session persistence

---

## Performance Optimization

1. **Memoize expensive computations**: Use `useMemo` for pipeline filtering
2. **Lazy load expanded details**: Only compute when accordion opens
3. **Pagination**: For large pipeline lists (50+), implement pagination
4. **Caching**: Cache optimization results in session
5. **Debouncing**: Debounce API calls when filtering

---

## Accessibility

- [ ] ARIA labels on all interactive elements
- [ ] Keyboard navigation support
- [ ] Color contrast compliance
- [ ] Screen reader support
- [ ] Mobile responsive design

---

## Future Enhancements

1. **Visualization**: Add interactive Pareto front chart
2. **Comparison**: Allow side-by-side comparison of solutions
3. **Customization**: Let users tweak parameters and regenerate
4. **History**: Show previous optimization runs
5. **Reporting**: Export results as PDF/CSV
