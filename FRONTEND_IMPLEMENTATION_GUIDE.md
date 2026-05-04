# Frontend Implementation Guide: Displaying Anonymization Changes

## Overview

The backend now returns detailed **change tracking information** for every anonymization. Your frontend needs to be updated to display these changes in a user-friendly way.

## What the Frontend Will Receive

After anonymization, the API response includes:

```json
{
  "message": "Anonymization completed successfully",
  "change_tracking": {
    "total_columns_changed": 5,
    "total_cells_changed": 120,
    "column_changes": [
      {
        "column_name": "name",
        "column_type": "direct_identifier",
        "anonymization_method": "suppression",
        "original_unique_values": 100,
        "anonymized_unique_values": 1,
        "cells_modified": 100,
        "sample_changes": [
          {"original": "John Smith", "anonymized": "[SUPPRESSED]"},
          {"original": "Jane Doe", "anonymized": "[SUPPRESSED]"}
        ]
      },
      {
        "column_name": "age",
        "column_type": "quasi_identifier",
        "anonymization_method": "generalization_and_suppression",
        "original_unique_values": 50,
        "anonymized_unique_values": 5,
        "cells_modified": 80,
        "sample_changes": [
          {"original": "25", "anonymized": "20-29"},
          {"original": "45", "anonymized": "40-49"}
        ]
      }
    ],
    "row_changes": [
      {
        "row_index": 0,
        "changed_columns": ["name", "email", "age"],
        "changes": {
          "name": {"original": "John Smith", "anonymized": "[SUPPRESSED]"},
          "email": {"original": "john@email.com", "anonymized": "[SUPPRESSED]"},
          "age": {"original": "25", "anonymized": "20-29"}
        }
      }
    ]
  }
}
```

## Recommended Frontend Components

### 1. Change Summary Card

**Location**: Top of anonymization results page

```tsx
// Components/AnonymizationChangesSummary.tsx
interface ChangeSummaryProps {
  changeTracking: {
    total_columns_changed: number;
    total_cells_changed: number;
  };
  originalRowCount: number;
  originalColumnCount: number;
}

export const AnonymizationChangesSummary: React.FC<ChangeSummaryProps> = ({
  changeTracking,
  originalRowCount,
  originalColumnCount,
}) => {
  const cellPercentage = (changeTracking.total_cells_changed / (originalRowCount * originalColumnCount)) * 100;
  const columnPercentage = (changeTracking.total_columns_changed / originalColumnCount) * 100;

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
      <h3 className="text-lg font-semibold mb-4">📊 Anonymization Changes Summary</h3>
      
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-sm text-gray-600">Columns Modified</p>
          <p className="text-2xl font-bold text-blue-600">
            {changeTracking.total_columns_changed}/{originalColumnCount}
          </p>
          <p className="text-xs text-gray-500">({columnPercentage.toFixed(1)}%)</p>
        </div>
        
        <div>
          <p className="text-sm text-gray-600">Cells Changed</p>
          <p className="text-2xl font-bold text-green-600">
            {changeTracking.total_cells_changed.toLocaleString()}
          </p>
          <p className="text-xs text-gray-500">({cellPercentage.toFixed(1)}%)</p>
        </div>
      </div>
    </div>
  );
};
```

### 2. Column Changes Table

**Location**: Mid-section showing each column's transformation

```tsx
// Components/ColumnChangesTable.tsx
interface ColumnChangeProps {
  columnChanges: Array<{
    column_name: string;
    column_type: string;
    anonymization_method: string;
    original_unique_values: number;
    anonymized_unique_values: number;
    cells_modified: number;
    sample_changes: Array<{original: string; anonymized: string}>;
  }>;
}

export const ColumnChangesTable: React.FC<ColumnChangeProps> = ({ columnChanges }) => {
  const getTypeColor = (type: string) => {
    switch(type) {
      case 'direct_identifier': return 'bg-red-100 text-red-800';
      case 'quasi_identifier': return 'bg-yellow-100 text-yellow-800';
      case 'sensitive_attribute': return 'bg-purple-100 text-purple-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getMethodIcon = (method: string) => {
    switch(method) {
      case 'suppression': return '🔒';
      case 'generalization_and_suppression': return '📊';
      case 'binning': return '📈';
      case 'suppress_rare_values': return '🚫';
      default: return '⚙️';
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-gray-100 border-b">
            <th className="text-left p-3 font-semibold">Column</th>
            <th className="text-left p-3 font-semibold">Type</th>
            <th className="text-left p-3 font-semibold">Method</th>
            <th className="text-center p-3 font-semibold">Unique Values</th>
            <th className="text-center p-3 font-semibold">Cells Changed</th>
            <th className="text-left p-3 font-semibold">Samples</th>
          </tr>
        </thead>
        <tbody>
          {columnChanges.map((col, idx) => (
            <tr key={idx} className="border-b hover:bg-gray-50">
              <td className="p-3 font-medium">{col.column_name}</td>
              <td className="p-3">
                <span className={`px-2 py-1 rounded text-xs font-semibold ${getTypeColor(col.column_type)}`}>
                  {col.column_type.replace(/_/g, ' ')}
                </span>
              </td>
              <td className="p-3">
                <span title={col.anonymization_method}>
                  {getMethodIcon(col.anonymization_method)} {col.anonymization_method.replace(/_/g, ' ')}
                </span>
              </td>
              <td className="p-3 text-center">
                <span className="text-sm">
                  {col.original_unique_values} → {col.anonymized_unique_values}
                </span>
              </td>
              <td className="p-3 text-center">
                <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded">
                  {col.cells_modified}
                </span>
              </td>
              <td className="p-3">
                <details className="text-sm">
                  <summary className="cursor-pointer text-blue-600 hover:underline">
                    View samples ({col.sample_changes.length})
                  </summary>
                  <ul className="mt-2 space-y-1 ml-2 text-gray-700">
                    {col.sample_changes.map((change, idx) => (
                      <li key={idx}>
                        <code className="text-xs bg-gray-100 px-1 rounded">
                          "{change.original}" → "{change.anonymized}"
                        </code>
                      </li>
                    ))}
                  </ul>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
```

### 3. Row-Level Changes

**Location**: Bottom section showing sample row transformations

```tsx
// Components/RowChangesPreview.tsx
interface RowChangeProps {
  rowChanges: Array<{
    row_index: number;
    changed_columns: string[];
    changes: Record<string, {original: string; anonymized: string}>;
  }>;
}

export const RowChangesPreview: React.FC<RowChangeProps> = ({ rowChanges }) => {
  return (
    <div className="space-y-4">
      <h3 className="font-semibold">Row-by-Row Changes (First 10 Samples)</h3>
      
      {rowChanges.slice(0, 10).map((row) => (
        <div key={row.row_index} className="border rounded-lg p-4 bg-gray-50">
          <p className="font-semibold text-sm mb-2">Row {row.row_index}</p>
          
          <p className="text-xs text-gray-600 mb-2">
            Modified columns: <span className="font-mono text-blue-600">{row.changed_columns.join(', ')}</span>
          </p>
          
          <div className="space-y-1">
            {Object.entries(row.changes).map(([col, changes]) => (
              <div key={col} className="text-sm flex items-center gap-2">
                <span className="font-medium text-gray-700 min-w-24">{col}:</span>
                <span className="line-through text-red-600">"{changes.original}"</span>
                <span className="text-green-600">→ "{changes.anonymized}"</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};
```

### 4. Complete Page Layout

```tsx
// pages/AnonymizationResults.tsx
export const AnonymizationResults: React.FC = () => {
  const { changeTracking, sampleData, metrics } = useAnonymizationResults();

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b pb-4">
        <h1 className="text-3xl font-bold">✅ Anonymization Completed</h1>
        <p className="text-gray-600">Your data has been anonymized and protected</p>
      </div>

      {/* Changes Summary */}
      <AnonymizationChangesSummary 
        changeTracking={changeTracking}
        originalRowCount={metrics.original_rows}
        originalColumnCount={metrics.original_columns}
      />

      {/* Tabs */}
      <Tabs defaultValue="columns">
        {/* Tab 1: Column Changes */}
        <TabsContent value="columns">
          <ColumnChangesTable columnChanges={changeTracking.column_changes} />
        </TabsContent>

        {/* Tab 2: Row Changes */}
        <TabsContent value="rows">
          <RowChangesPreview rowChanges={changeTracking.row_changes} />
        </TabsContent>

        {/* Tab 3: Sample Data */}
        <TabsContent value="preview">
          <SampleDataPreview data={sampleData} />
        </TabsContent>

        {/* Tab 4: Before/After */}
        <TabsContent value="comparison">
          <BeforeAfterComparison />
        </TabsContent>
      </Tabs>

      {/* Actions */}
      <div className="flex gap-4">
        <button className="bg-green-600 text-white px-4 py-2 rounded">
          ✓ Download Anonymized Data
        </button>
        <button className="bg-gray-600 text-white px-4 py-2 rounded">
          📋 Download Report
        </button>
      </div>
    </div>
  );
};
```

## CSS Styling Ideas

```css
/* Color-code column types */
.column-type-direct-identifier {
  background-color: #fee2e2;
  color: #991b1b;
}

.column-type-quasi-identifier {
  background-color: #fef3c7;
  color: #92400e;
}

.column-type-sensitive-attribute {
  background-color: #f3e8ff;
  color: #6b21a8;
}

/* Highlight changed cells */
.cell-changed {
  background-color: #fef08a;
  position: relative;
}

.cell-changed::after {
  content: "✓ changed";
  position: absolute;
  top: -5px;
  right: -5px;
  font-size: 0.65rem;
  background: #fbbf24;
  color: white;
  padding: 1px 4px;
  border-radius: 2px;
}

/* Method badges */
.method-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.85rem;
  font-weight: 500;
}

.method-suppression {
  background: #fee2e2;
  color: #991b1b;
}

.method-generalization {
  background: #fef3c7;
  color: #92400e;
}

.method-binning {
  background: #dbeafe;
  color: #1e40af;
}
```

## Integration Steps

### Step 1: Update Anonymization Results Page
```tsx
// Modify the page that displays anonymization results
// Add the new components after basic metrics

import { AnonymizationChangesSummary } from '@/components/AnonymizationChangesSummary';
import { ColumnChangesTable } from '@/components/ColumnChangesTable';
import { RowChangesPreview } from '@/components/RowChangesPreview';

// In your result handling:
const handleAnonymizationResult = (response) => {
  // ... existing code ...
  
  // NEW: Display change tracking
  setChangeTracking(response.change_tracking);
};
```

### Step 2: Add Change Tracking Hooks
```tsx
// hooks/useChangeTracking.ts
export const useChangeTracking = (data: any) => {
  return {
    totalColumnsChanged: data.change_tracking.total_columns_changed,
    totalCellsChanged: data.change_tracking.total_cells_changed,
    columnChanges: data.change_tracking.column_changes,
    rowChanges: data.change_tracking.row_changes,
  };
};
```

### Step 3: Update Compare View
```tsx
// When showing before/after comparison
// Highlight which columns/cells were changed

const getRowHighlight = (rowIndex: number) => {
  const row = changeTracking.row_changes.find(r => r.row_index === rowIndex);
  return row ? row.changed_columns : [];
};
```

## Display Recommendations

### For Data Privacy Officers
"Show me which columns were protected and how many records were affected"
- ✅ Use the summary card
- ✅ Use the column table
- ✅ Color-code by sensitivity level

### For Data Scientists
"Show me which columns changed so I know what utility remains"
- ✅ Show unique value counts (before/after)
- ✅ Show sample transformations
- ✅ Show cells_modified percentage

### For IT Auditors
"Show me what changed so I can audit the process"
- ✅ Show row-by-row changes
- ✅ Show exact transformations
- ✅ Show anonymization method used

## Common Questions from Users

### Q: "What does [SUPPRESSED] mean?"
A: Direct identifiers like names and emails are completely hidden to prevent identification.

### Q: "Why did my age change from 25 to '20-29'?"
A: Age ranges reduce the uniqueness of records, making it harder to identify individuals.

### Q: "Was my income data changed?"
A: Yes, income is rounded to the nearest 1000 to protect against financial disclosure.

### Q: "How many rows were affected?"
A: Check the summary card - shows total cells changed out of total cells.

## Testing Checklist

- [ ] Summary shows correct column and cell counts
- [ ] All column types display with correct colors
- [ ] Sample transformations show before/after values
- [ ] Row changes display first 20 samples
- [ ] No data leakage in display
- [ ] Mobile responsive layout
- [ ] Expandable sections work properly
- [ ] Download functionality works
- [ ] Comparison view highlights changes
- [ ] Works with large datasets (100K+ rows)

## Performance Considerations

- **Lazy load** row samples (only first 20 shown)
- **Virtualize** large lists if needed
- **Cache** change tracking data
- **Debounce** tab switches

## Accessibility

- Add `aria-labels` to all buttons and icons
- Ensure color-coding isn't the only indicator
- Use semantic HTML
- Keyboard navigation for tabs
- Screen reader friendly

## Future Enhancements

1. **Export Report**: Save change summary as PDF
2. **Customization**: Let users choose what to display
3. **Filtering**: Filter columns by type or method
4. **Statistics**: Chart showing distribution of methods
5. **Comparison Tool**: Visual diff of before/after

---

**Note**: All backend changes are complete. Frontend just needs to display the new `change_tracking` field that's now included in API responses.
