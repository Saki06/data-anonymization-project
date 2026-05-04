'use client';

import React from 'react';

interface ParetoPoint {
  x: number;
  y: number;
  id: number;
  label: string;
  selected?: boolean;
}

interface ParetoFrontVisualizationProps {
  points: ParetoPoint[];
  onPointClick?: (id: number) => void;
  width?: number;
  height?: number;
  title?: string;
}

export default function ParetoFrontVisualization({
  points,
  onPointClick,
  width = 600,
  height = 400,
  title = 'Pareto Front',
}: ParetoFrontVisualizationProps) {
  if (!points || points.length === 0) {
    return (
      <div className="flex items-center justify-center p-8 text-gray-500">
        No data available to visualize
      </div>
    );
  }

  // Calculate padding
  const padding = 50;
  const chartWidth = width - 2 * padding;
  const chartHeight = height - 2 * padding;

  // Find min/max values
  const xValues = points.map((p) => p.x);
  const yValues = points.map((p) => p.y);
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);

  // Add padding to scales
  const xRange = maxX - minX || 1;
  const yRange = maxY - minY || 1;
  const xMin = minX - xRange * 0.1;
  const xMax = maxX + xRange * 0.1;
  const yMin = minY - yRange * 0.1;
  const yMax = maxY + yRange * 0.1;

  // Scale functions
  const scaleX = (val: number) => padding + ((val - xMin) / (xMax - xMin)) * chartWidth;
  const scaleY = (val: number) => height - padding - ((val - yMin) / (yMax - yMin)) * chartHeight;

  // Sort points to draw Pareto front line
  const sortedPoints = [...points].sort((a, b) => a.x - b.x);

  return (
    <svg width={width} height={height} className="border border-gray-300 rounded bg-white">
      {/* Grid */}
      <defs>
        <pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse">
          <path
            d="M 50 0 L 0 0 0 50"
            fill="none"
            stroke="rgba(200,200,200,0.1)"
            strokeWidth="0.5"
          />
        </pattern>
      </defs>
      <rect x={padding} y={padding} width={chartWidth} height={chartHeight} fill="url(#grid)" />

      {/* Axes */}
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="black" strokeWidth="2" />
      <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="black" strokeWidth="2" />

      {/* Axis Labels */}
      <text x={width / 2} y={height - 10} textAnchor="middle" fontSize="12" fontWeight="bold">
        Privacy Score
      </text>
      <text x={20} y={height / 2} textAnchor="middle" fontSize="12" fontWeight="bold" transform={`rotate(-90 20 ${height / 2})`}>
        Utility Score
      </text>

      {/* Pareto Front Line */}
      <polyline
        points={sortedPoints.map((p) => `${scaleX(p.x)},${scaleY(p.y)}`).join(' ')}
        fill="none"
        stroke="rgba(59, 130, 246, 0.3)"
        strokeWidth="2"
        strokeDasharray="5,5"
      />

      {/* Points */}
      {points.map((point) => {
        const x = scaleX(point.x);
        const y = scaleY(point.y);

        return (
          <g key={point.id}>
            <circle
              cx={x}
              cy={y}
              r={point.selected ? 8 : 5}
              fill={point.selected ? '#dc2626' : '#3b82f6'}
              stroke="white"
              strokeWidth="2"
              style={{
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onClick={() => onPointClick?.(point.id)}
            />
            <title>{point.label}</title>
          </g>
        );
      })}

      {/* Ideal Point (0,0) */}
      <circle cx={scaleX(0)} cy={scaleY(0)} r="4" fill="green" stroke="white" strokeWidth="2" opacity="0.5" />
      <text x={scaleX(0) + 10} y={scaleY(0) - 5} fontSize="10" fill="green">
        Ideal
      </text>
    </svg>
  );
}
