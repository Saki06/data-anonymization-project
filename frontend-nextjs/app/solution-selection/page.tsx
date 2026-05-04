'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSession, API_BASE } from '@/lib/SessionContext';
import Breadcrumb from '@/components/Breadcrumb';
import StatusBadge from '@/components/StatusBadge';
import {
  ChevronDown,
  ChevronUp,
  Zap,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  CheckCircle,
  BarChart3,
  Target,
} from 'lucide-react';

interface ParetoSolution {
  pipeline_id: number;
  privacy_score: number;
  utility_score: number;
  distance_to_ideal: number;
  rank: number;
  k_value?: number;
  l_value?: number;
  t_value?: number;
  pipeline_description?: string;
}

interface OptimizationResult {
  pareto_front: ParetoSolution[];
  total_pipelines_evaluated: number;
  best_solution: ParetoSolution;
  optimization_metrics?: {
    privacy_improvement: number;
    utility_preservation: number;
  };
}

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

export default function SolutionSelectionPage() {
  const router = useRouter();
  const { sessionId, API_BASE: apiBaseUrl } = useSession();
  const [state, setState] = useState<SelectionState>({
    loading: true,
    success: false,
    error: null,
    results: null,
    selectedMode: 'auto',
    userSelectedId: null,
    expandedSolution: null,
    executing: false,
  });

  // Load optimization results
  const loadOptimizationResults = async () => {
    if (!sessionId) {
      setState((s) => ({ ...s, error: 'Session not found', loading: false }));
      return;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/anonymization/get-pareto-front`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });

      if (!response.ok) {
        throw new Error('Failed to load optimization results');
      }

      const data = await response.json();
      setState((s) => ({
        ...s,
        results: data,
        success: true,
        loading: false,
      }));
    } catch (err) {
      setState((s) => ({
        ...s,
        error: err instanceof Error ? err.message : 'Unknown error',
        loading: false,
      }));
    }
  };

  // Select solution based on user choice
  const selectSolution = async (pipelineId: number) => {
    if (!sessionId) {
      setState((s) => ({ ...s, error: 'Session not found' }));
      return;
    }

    setState((s) => ({ ...s, executing: true, error: null }));

    try {
      const response = await fetch(`${apiBaseUrl}/anonymization/select-solution`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          pipeline_id: pipelineId,
          mode: state.selectedMode,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to select solution');
      }

      setState((s) => ({ ...s, userSelectedId: pipelineId, executing: false }));

      // Navigate to execution
      setTimeout(() => {
        router.push('/anonymization?step=execute');
      }, 1500);
    } catch (err) {
      setState((s) => ({
        ...s,
        error: err instanceof Error ? err.message : 'Selection failed',
        executing: false,
      }));
    }
  };

  useEffect(() => {
    loadOptimizationResults();
  }, []);

  const bestSolution = state.results?.best_solution;
  const paretoFront = state.results?.pareto_front || [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <div className="container mx-auto px-4 py-8">
        {/* Breadcrumb */}
        <Breadcrumb
          items={[
            { label: 'Dashboard', href: '/dashboard' },
            { label: 'Anonymization', href: '/anonymization' },
            { label: 'Solution Selection' },
          ]}
        />

        {/* Header */}
        <div className="mt-8 mb-8">
          <h1 className="text-4xl font-bold text-slate-900 dark:text-white mb-2">Pareto Front Analysis</h1>
          <p className="text-lg text-slate-600 dark:text-slate-400">
            Select the best privacy-utility trade-off from {paretoFront.length} optimal solutions
          </p>
        </div>

        {/* Error Alert */}
        {state.error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-semibold text-red-900 dark:text-red-100">Error</h3>
              <p className="text-red-800 dark:text-red-200">{state.error}</p>
            </div>
          </div>
        )}

        {/* Loading State */}
        {state.loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin">
              <BarChart3 className="w-8 h-8 text-blue-500" />
            </div>
            <p className="mt-4 text-slate-600 dark:text-slate-400">Loading optimization results...</p>
          </div>
        )}

        {/* Success Message */}
        {state.userSelectedId && (
          <div className="mb-6 p-4 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-lg flex items-start gap-3">
            <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-semibold text-green-900 dark:text-green-100">Solution Selected</h3>
              <p className="text-green-800 dark:text-green-200">Proceeding to anonymization execution...</p>
            </div>
          </div>
        )}

        {!state.loading && state.results && (
          <>
            {/* Selection Mode */}
            <div className="mb-8 flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="mode"
                  value="auto"
                  checked={state.selectedMode === 'auto'}
                  onChange={() => setState((s) => ({ ...s, selectedMode: 'auto' }))}
                  className="w-4 h-4"
                />
                <span className="text-slate-700 dark:text-slate-300">Auto-Select Best</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="mode"
                  value="human"
                  checked={state.selectedMode === 'human'}
                  onChange={() => setState((s) => ({ ...s, selectedMode: 'human' }))}
                  className="w-4 h-4"
                />
                <span className="text-slate-700 dark:text-slate-300">Manual Selection</span>
              </label>
            </div>

            {/* Best Solution Recommendation */}
            {bestSolution && (
              <div className="mb-8 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950 dark:to-indigo-950 rounded-lg p-6 border border-blue-200 dark:border-blue-800">
                <div className="flex items-start gap-4 mb-4">
                  <div className="bg-blue-100 dark:bg-blue-900 rounded-full p-3">
                    <Target className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Recommended Solution</h3>
                    <p className="text-slate-600 dark:text-slate-400 text-sm">Best privacy-utility trade-off (Rank #1)</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                  <div>
                    <div className="text-sm text-slate-600 dark:text-slate-400">Privacy Score</div>
                    <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                      {bestSolution.privacy_score.toFixed(3)}
                    </div>
                    <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">↓ Lower is better</div>
                  </div>
                  <div>
                    <div className="text-sm text-slate-600 dark:text-slate-400">Utility Score</div>
                    <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                      {bestSolution.utility_score.toFixed(3)}
                    </div>
                    <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">↓ Lower is better</div>
                  </div>
                  <div>
                    <div className="text-sm text-slate-600 dark:text-slate-400">Distance to Ideal</div>
                    <div className="text-2xl font-bold text-slate-900 dark:text-white">
                      {bestSolution.distance_to_ideal.toFixed(3)}
                    </div>
                    <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">↓ Optimal point</div>
                  </div>
                  <div>
                    <div className="text-sm text-slate-600 dark:text-slate-400">Target Values</div>
                    <div className="text-sm font-mono text-slate-700 dark:text-slate-300 mt-1">
                      k={bestSolution.k_value} | l={bestSolution.l_value} | t={bestSolution.t_value?.toFixed(2)}
                    </div>
                  </div>
                </div>

                {state.selectedMode === 'auto' && (
                  <button
                    onClick={() => selectSolution(bestSolution.pipeline_id)}
                    disabled={state.executing}
                    className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-blue-400 transition-colors font-medium flex items-center justify-center gap-2"
                  >
                    {state.executing ? (
                      <>
                        <div className="animate-spin">
                          <Zap className="w-4 h-4" />
                        </div>
                        Processing...
                      </>
                    ) : (
                      <>
                        <CheckCircle className="w-4 h-4" />
                        Select Recommended Solution
                      </>
                    )}
                  </button>
                )}
              </div>
            )}

            {/* Pareto Front Solutions */}
            <div className="mb-8">
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-4">All Pareto Front Solutions</h2>
              <p className="text-slate-600 dark:text-slate-400 mb-6">
                Total pipelines evaluated: {state.results?.total_pipelines_evaluated} | Optimal solutions: {paretoFront.length}
              </p>

              <div className="space-y-3">
                {paretoFront.map((solution) => (
                  <div
                    key={solution.pipeline_id}
                    className={`bg-white dark:bg-slate-800 rounded-lg border-2 transition-all ${
                      state.userSelectedId === solution.pipeline_id
                        ? 'border-green-500 bg-green-50 dark:bg-green-950'
                        : 'border-slate-200 dark:border-slate-700'
                    }`}
                  >
                    {/* Solution Header */}
                    <div
                      className="p-6 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                      onClick={() =>
                        setState((s) => ({
                          ...s,
                          expandedSolution: s.expandedSolution === solution.pipeline_id ? null : solution.pipeline_id,
                        }))
                      }
                    >
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <span className="text-2xl font-bold text-slate-900 dark:text-white w-10">#{solution.rank}</span>
                          <div>
                            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                              Pipeline {solution.pipeline_id}
                            </h3>
                            <p className="text-sm text-slate-600 dark:text-slate-400">
                              {solution.pipeline_description || 'Optimized anonymization pipeline'}
                            </p>
                          </div>
                        </div>

                        {state.userSelectedId === solution.pipeline_id && (
                          <div className="px-3 py-1 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200 text-xs font-medium rounded-full flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" />
                            Selected
                          </div>
                        )}
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        <div className="bg-blue-50 dark:bg-blue-950 rounded p-3">
                          <div className="text-xs text-slate-600 dark:text-slate-400 font-medium">Privacy Score</div>
                          <div className="text-lg font-bold text-blue-600 dark:text-blue-400 mt-1">
                            {solution.privacy_score.toFixed(3)}
                          </div>
                        </div>

                        <div className="bg-green-50 dark:bg-green-950 rounded p-3">
                          <div className="text-xs text-slate-600 dark:text-slate-400 font-medium">Utility Score</div>
                          <div className="text-lg font-bold text-green-600 dark:text-green-400 mt-1">
                            {solution.utility_score.toFixed(3)}
                          </div>
                        </div>

                        <div className="bg-purple-50 dark:bg-purple-950 rounded p-3">
                          <div className="text-xs text-slate-600 dark:text-slate-400 font-medium">Distance</div>
                          <div className="text-lg font-bold text-purple-600 dark:text-purple-400 mt-1">
                            {solution.distance_to_ideal.toFixed(3)}
                          </div>
                        </div>

                        <div className="bg-yellow-50 dark:bg-yellow-950 rounded p-3">
                          <div className="text-xs text-slate-600 dark:text-slate-400 font-medium">k-value</div>
                          <div className="text-lg font-bold text-yellow-600 dark:text-yellow-400 mt-1">
                            {solution.k_value || 'N/A'}
                          </div>
                        </div>

                        <div className="bg-indigo-50 dark:bg-indigo-950 rounded p-3">
                          <div className="text-xs text-slate-600 dark:text-slate-400 font-medium">t-value</div>
                          <div className="text-lg font-bold text-indigo-600 dark:text-indigo-400 mt-1">
                            {solution.t_value?.toFixed(2) || 'N/A'}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Expanded Details */}
                    {state.expandedSolution === solution.pipeline_id && (
                      <div className="border-t border-slate-200 dark:border-slate-700 p-6 bg-slate-50 dark:bg-slate-900">
                        <div className="mb-4">
                          <h4 className="font-semibold text-slate-900 dark:text-white mb-2">Analysis</h4>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="bg-white dark:bg-slate-800 rounded p-3 border border-slate-200 dark:border-slate-700">
                              <div className="text-sm text-slate-600 dark:text-slate-400 font-medium">Privacy Characteristics</div>
                              <ul className="text-sm text-slate-700 dark:text-slate-300 mt-2 space-y-1">
                                <li>• k-anonymity: {solution.k_value}</li>
                                <li>• l-diversity: {solution.l_value}</li>
                                <li>• t-closeness: {solution.t_value?.toFixed(3)}</li>
                              </ul>
                            </div>
                            <div className="bg-white dark:bg-slate-800 rounded p-3 border border-slate-200 dark:border-slate-700">
                              <div className="text-sm text-slate-600 dark:text-slate-400 font-medium">Quality Metrics</div>
                              <ul className="text-sm text-slate-700 dark:text-slate-300 mt-2 space-y-1">
                                <li>• Privacy Score: {solution.privacy_score.toFixed(4)}</li>
                                <li>• Utility Score: {solution.utility_score.toFixed(4)}</li>
                                <li>• Distance to Ideal: {solution.distance_to_ideal.toFixed(4)}</li>
                              </ul>
                            </div>
                          </div>
                        </div>

                        {state.selectedMode === 'human' && (
                          <button
                            onClick={() => selectSolution(solution.pipeline_id)}
                            disabled={state.executing}
                            className="w-full px-6 py-2 bg-slate-900 dark:bg-slate-700 text-white rounded-lg hover:bg-slate-800 dark:hover:bg-slate-600 disabled:bg-slate-400 transition-colors font-medium"
                          >
                            {state.executing && state.userSelectedId === solution.pipeline_id ? 'Selecting...' : 'Select This Solution'}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Summary Stats */}
            {state.results?.optimization_metrics && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <div className="bg-white dark:bg-slate-800 rounded-lg p-6 border border-slate-200 dark:border-slate-700">
                  <div className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">Privacy Improvement</div>
                  <div className="text-3xl font-bold text-blue-600 dark:text-blue-400">
                    {(state.results.optimization_metrics.privacy_improvement * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="bg-white dark:bg-slate-800 rounded-lg p-6 border border-slate-200 dark:border-slate-700">
                  <div className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">Utility Preservation</div>
                  <div className="text-3xl font-bold text-green-600 dark:text-green-400">
                    {(state.results.optimization_metrics.utility_preservation * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex gap-4">
              <button
                onClick={() => router.push('/pipeline-generation')}
                className="px-6 py-2 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors font-medium"
              >
                Back to Pipelines
              </button>
              <button
                onClick={() => router.push('/anonymization')}
                className="px-6 py-2 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors font-medium"
              >
                Cancel
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
