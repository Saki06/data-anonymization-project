'use client';

interface DataTableProps {
  columns?: string[];
  rows?: Record<string, unknown>[];
  maxRows?: number;
}

export default function DataTable({ columns, rows, maxRows = 10 }: DataTableProps) {
  const safeCols = columns ?? [];
  const safeRows = rows ?? [];

  if (safeCols.length === 0) return <p className="text-sm text-gray-500">No data available.</p>;

  const displayRows = safeRows.slice(0, maxRows);
  return (
    <div className="overflow-x-auto mt-3">
      <table className="data-table">
        <thead>
          <tr>
            {safeCols.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row, i) => (
            <tr key={i}>
              {safeCols.map((col) => (
                <td key={col}>{String(row[col] ?? '')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-sm text-gray-500 mt-1">
        Showing {displayRows.length} of {safeRows.length} rows
      </p>
    </div>
  );
}
