'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSession, API_BASE } from '@/lib/SessionContext';
import Breadcrumb from '@/components/Breadcrumb';
import StatusBadge from '@/components/StatusBadge';
import { ChevronDown, ChevronUp, Zap, TrendingUp, TrendingDown, AlertCircle, CheckCircle } from 'lucide-react';

interface AnonymizationStep {
  method: string;
  target_columns: string[];
  parameters: Record<string, unknown>;
}

interface AnonymizationPipeline {
  pipeline_id: number;
  steps: AnonymizationStep[];
  privacy_target: { k?: number; l?: number; t?: number };
  privacy_level: string;
  utility_impact: string;
  description: string;
}

interface GenerationState {
  loading: boolean;
  success: boolean;
  error: string | null;
  pipelines: AnonymizationPipeline[];
  selectedPipeline: number | null;
}

export default function PipelineGenerationPage() {
  const router = useRouter();
  const { sessionId, API_BASE: apiBaseUrl } = useSession();
  const [state, setState] = useState<GenerationState>({
    loading: false,
    success: false,
    error: null,
    pipelines: [],
    selectedPipeline: null,
  });
  const [expandedPipeline, setExpandedPipeline] = useState<number | null>(null);

  // Generate pipelines from previous analysis
  const generatePipelines = async () => {
    if (!sessionId) {
      setState((s) => ({ ...s, error: 'Session not found. Please start from dashboard.' }));
      return;
    }

    setState((s) => ({ ...s, loading: true, error: null }));

    try {
      const response = await fetch(`${apiBaseUrl}/anonymization/generate-pipelines`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          num_pipelines: 20,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to generate pipelines');
      }

      const data = await response.json();
      setState((s) => ({
        ...s,
        success: true,
        pipelines: data.pipelines || [],
        loading: false,
      }));
    } catch (err) {
      setState((s) => ({
        ...s,
        error: err instanceof Error ? err.message : 'Unknown error occurred',
        loading: false,
      }));
    }
  };

  // Proceed to optimization
  const proceedToOptimization = async () => {
    if (!sessionId || state.pipelines.length === 0) {
      setState((s) => ({ ...s, error: 'No pipelines available for optimization' }));
      return;
    }

    try {
      // Store pipeline selection in session
      const response = await fetch(`${apiBaseUrl}/anonymization/optimize-pipelines`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          pipelines: state.pipelines,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to optimize pipelines');
      }

      router.push('/solution-selection');
    } catch (err) {
      setState((s) => ({
        ...s,
        error: err instanceof Error ? err.message : 'Optimization failed',
      }));
    }
  };

  useEffect(() => {
    generatePipelines();
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <div className="container mx-auto px-4 py-8">
        {/* Breadcrumb */}
        <Breadcrumb
          items={[
            { label: 'Dashboard', href: '/dashboard' },
            { label: 'Anonymization', href: '/anonymization' },
            { label: 'Pipeline Generation' },
          ]}
        />

        {/* Header */}
        <div className="mt-8 mb-8">
          <h1 className="text-4xl font-bold text-slate-900 dark:text-white mb-2">Pipeline Generation</h1>
          <p className="text-lg text-slate-600 dark:text-slate-400">
            Generating diverse anonymization strategies combining different SDC methods
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
              <Zap className="w-8 h-8 text-blue-500" />
            </div>
            <p className="mt-4 text-slate-600 dark:text-slate-400">Generating pipelines...</p>
          </div>
        )}

        {/* Pipelines Grid */}
        {!state.loading && state.pipelines.length > 0 && (
          <>
            {/* Summary Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
              <div className="bg-white dark:bg-slate-800 rounded-lg p-6 border border-slate-200 dark:border-slate-700">
                <div className="text-sm font-medium text-slate-600 dark:text-slate-400">Total Pipelines</div>
                <div className="text-3xl font-bold text-slate-900 dark:text-white mt-2">{state.pipelines.length}</div>
              </div>
              <div className="bg-white dark:bg-slate-800 rounded-lg p-6 border border-slate-200 dark:border-slate-700">
                <div className="text-sm font-medium text-slate-600 dark:text-slate-400">Single-Method</div>
                <div className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-2">
                  {state.pipelines.filter((p) => p.steps.length === 1).length}
                </div>
              </div>
              <div className="bg-white dark:bg-slate-800 rounded-lg p-6 border border-slate-200 dark:border-slate-700">
                <div className="text-sm font-medium text-slate-600 dark:text-slate-400">Hybrid</div>
                <div className="text-3xl font-bold text-purple-600 dark:text-purple-400 mt-2">
                  {state.pipelines.filter((p) => p.steps.length > 1).length}
                </div>
              </div>
              <div className="bg-white dark:bg-slate-800 rounded-lg p-6 border border-slate-200 dark:border-slate-700">
                <div className="text-sm font-medium text-slate-600 dark:text-slate-400">Avg. Privacy Level</div>
                <div className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">High</div>
              </div>
            </div>

            {/* Pipelines List */}
            <div className="space-y-4">
              {state.pipelines.map((pipeline) => (
                <div
                  key={pipeline.pipeline_id}
                  className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden hover:shadow-lg transition-shadow"
                >
                  {/* Pipeline Header */}
                  <div
                    className="p-6 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    onClick={() =>
                      setExpandedPipeline(expandedPipeline === pipeline.pipeline_id ? null : pipeline.pipeline_id)
                    }
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                            Pipeline {pipeline.pipeline_id}
                          </h3>
                          <span className="px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 text-xs font-medium rounded-full">
                            {pipeline.steps.length}-{pipeline.steps.length === 1 ? 'step' : 'steps'}
                          </span>
                          <StatusBadge status={pipeline.privacy_level} />
                        </div>
                        <p className="text-slate-600 dark:text-slate-400 text-sm">{pipeline.description}</p>

                        {/* Privacy Targets */}
                        <div className="flex gap-4 mt-3">
                          {pipeline.privacy_target.k !== undefined && (
                            <div className="flex items-center gap-1 text-sm text-slate-700 dark:text-slate-300">
                              <TrendingDown className="w-4 h-4" />
                              <span>k={pipeline.privacy_target.k}</span>
                            </div>
                          )}
                          {pipeline.privacy_target.l !== undefined && (
                            <div className="flex items-center gap-1 text-sm text-slate-700 dark:text-slate-300">
                              <TrendingDown className="w-4 h-4" />
                              <span>l={pipeline.privacy_target.l}</span>
                            </div>
                          )}
                          {pipeline.privacy_target.t !== undefined && (
                            <div className="flex items-center gap-1 text-sm text-slate-700 dark:text-slate-300">
                              <TrendingDown className="w-4 h-4" />
                              <span>t={pipeline.privacy_target.t.toFixed(2)}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="text-right ml-4">
                        <div className="text-sm text-slate-600 dark:text-slate-400 mb-2">Utility Impact</div>
                        <div className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                          {pipeline.utility_impact}
                        </div>
                        {expandedPipeline === pipeline.pipeline_id ? (
                          <ChevronUp className="w-5 h-5 text-slate-400 ml-auto" />
                        ) : (
                          <ChevronDown className="w-5 h-5 text-slate-400 ml-auto" />
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {expandedPipeline === pipeline.pipeline_id && (
                    <div className="border-t border-slate-200 dark:border-slate-700 p-6 bg-slate-50 dark:bg-slate-900">
                      <h4 className="font-semibold text-slate-900 dark:text-white mb-4">Pipeline Steps</h4>
                      <div className="space-y-3">
                        {pipeline.steps.map((step, idx) => (
                          <div key={idx} className="bg-white dark:bg-slate-800 rounded p-3 border border-slate-200 dark:border-slate-700">
                            <div className="font-medium text-slate-900 dark:text-white mb-2">
                              Step {idx + 1}: {step.method}
                            </div>
                            <div className="text-sm text-slate-600 dark:text-slate-400 mb-2">
                              <span className="font-medium">Targets:</span> {step.target_columns.join(', ')}
                            </div>
                            <div className="text-sm text-slate-600 dark:text-slate-400">
                              <span className="font-medium">Parameters:</span>
                              <div className="ml-3 mt-1 space-y-1">
                                {Object.entries(step.parameters).map(([key, val]) => (
                                  <div key={key}>
                                    {key}: <span className="font-mono text-slate-700 dark:text-slate-300">{String(val)}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Action Buttons */}
            <div className="mt-8 flex gap-4">
              <button
                onClick={() => router.push('/anonymization')}
                className="px-6 py-2 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors font-medium"
              >
                Back
              </button>
              <button
                onClick={proceedToOptimization}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium flex items-center gap-2"
              >
                <Zap className="w-4 h-4" />
                Optimize with NSGA-II
              </button>
            </div>
          </>
        )}

        {/* Empty State */}
        {!state.loading && state.pipelines.length === 0 && !state.error && (
          <div className="text-center py-12">
            <AlertCircle className="w-12 h-12 text-slate-400 mx-auto mb-4" />
            <p className="text-slate-600 dark:text-slate-400">No pipelines generated</p>
          </div>
        )}
      </div>
    </div>
  );
}
