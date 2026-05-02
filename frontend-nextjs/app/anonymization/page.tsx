'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useSession, API_BASE } from '@/lib/SessionContext';
import Breadcrumb from '@/components/Breadcrumb';
import StatusBadge from '@/components/StatusBadge';
import DataTable from '@/components/DataTable';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Recommendation {
  method: string;
  details?: string;
  explanation?: string;
  confidence?: number;
  privacy_level?: string;
  utility_impact?: string;
}

interface RecommendationSet {
  primary_method: string;
  secondary_methods?: string[];
  hybrid_approach?: boolean;
  overall_privacy_level?: string;
  overall_utility_impact?: string;
  additional_notes?: string;
  recommendations: Recommendation[];
}

interface AnalysisResult {
  risk_score: number;
  statistics: {
    total_records: number;
    total_qis: number;
    unique_combinations: number;
    min_equivalence_class_size: number;
    avg_equivalence_class_size: number;
  };
  risk_metrics?: { unique_records_ratio?: number };
  detected_problems?: { problem: string; severity: string; condition: string }[];
  triggered_rules?: string[];
  recommendations?: RecommendationSet;
  optimal_parameters?: { k: number; l: number; t: number; generalization_level?: number };
  optimization_results?: { pareto_front?: number[][] | number; pareto_front_size?: number };
}

interface ConstraintResult {
  is_valid: boolean;
  message?: string;
  actual_value?: number | string;
  required_value?: number | string;
}

interface ExecutionResult {
  parameters_used: { k: number; l: number; t: number };
  metrics: {
    suppression_ratio: number;
    min_equivalence_class_size: number;
    avg_equivalence_class_size?: number;
  };
  applied_methods?: string[];
  validation?: Record<string, ConstraintResult>;
  sample_data?: Record<string, unknown>[];
  columns?: string[];
}

interface ColumnComparison {
  column_name: string;
  is_quasi_identifier: boolean;
  original_unique: number;
  anonymized_unique: number;
  changes_detected: boolean;
  suppressed_values?: number;
  changed_values?: number;
}

interface SampleRow {
  original: Record<string, unknown>;
  anonymized: Record<string, unknown>;
  differences: string[];
}

interface CompareResult {
  original_shape: [number, number];
  anonymized_shape: [number, number];
  quasi_identifiers?: string[];
  sensitive_attributes?: string[];
  statistics_comparison?: {
    combination_reduction: number;
    modified_qi_rows: number;
    original_unique_qi_combinations?: number;
    anonymized_unique_qi_combinations?: number;
    suppressed_qi_cells?: number;
    total_qi_cells?: number;
  };
  column_comparison?: ColumnComparison[];
  sample_comparison?: SampleRow[];
  // Risk comparison metrics (new)
  risk_comparison?: {
    pre_risk_metrics?: {
      prosecutor_risk?: number;
      journalist_risk?: number;
      marketer_risk?: number;
      linkage_risk?: number;
      unique_records_ratio?: number;
      min_group_size?: number;
      avg_group_size?: number;
    };
    post_risk_metrics?: {
      prosecutor_risk?: number;
      journalist_risk?: number;
      marketer_risk?: number;
      linkage_risk?: number;
      unique_records_ratio?: number;
      min_group_size?: number;
      avg_group_size?: number;
    };
    improvement?: {
      prosecutor_risk_reduction?: number;
      journalist_risk_reduction?: number;
      unique_records_reduction?: number;
      overall_risk_reduction?: number;
    };
  };
}

type Tab = 'analyze' | 'plan' | 'execute' | 'compare' | 'export';

// ─── Pareto Canvas ────────────────────────────────────────────────────────────

function ParetoChart({ paretoFront }: { paretoFront: number[][] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const pad = 44;
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad, pad); ctx.lineTo(pad, h - pad); ctx.lineTo(w - pad, h - pad);
    ctx.stroke();

    ctx.fillStyle = '#94a3b8';
    ctx.font = '11px Arial';
    ctx.fillText('Disclosure risk \u2192', pad + 4, h - 10);
    ctx.save();
    ctx.translate(14, h - pad - 4);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('Utility loss \u2192', 0, 0);
    ctx.restore();

    const pts = (paretoFront || []).filter(p => Array.isArray(p) && p.length >= 2 && isFinite(p[0]) && isFinite(p[1]));
    if (!pts.length) {
      ctx.fillStyle = '#94a3b8';
      ctx.fillText('No Pareto front available (install pymoo for full NSGA\u2011II).', pad + 10, h / 2);
      return;
    }

    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const xmin = Math.min(...xs), xmax = Math.max(...xs);
    const ymin = Math.min(...ys), ymax = Math.max(...ys);
    const xSpan = (xmax - xmin) || 1, ySpan = (ymax - ymin) || 1;

    const sx = (x: number) => pad + ((x - xmin) / xSpan) * (w - 2 * pad);
    const sy = (y: number) => (h - pad) - ((y - ymin) / ySpan) * (h - 2 * pad);

    ctx.fillStyle = '#667eea';
    pts.forEach(p => {
      ctx.beginPath();
      ctx.arc(sx(p[0]), sy(p[1]), 4, 0, Math.PI * 2);
      ctx.fill();
    });
  }, [paretoFront]);

  return (
    <canvas
      ref={canvasRef}
      width={860}
      height={300}
      className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
    />
  );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KpiCard({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex flex-col gap-1 p-4 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl">
      <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
      <div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{value}</div>
      {note && <div className="text-xs text-slate-400 dark:text-slate-500">{note}</div>}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

function AnonymizationInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { sessionId: ctxSid, quasiIdentifiers: ctxQIs, sensitiveAttributes: ctxSens, datasetInfo } = useSession();

  const sid   = searchParams.get('session_id') || ctxSid || '';
  const qiParam   = searchParams.get('quasi_identifiers');
  const sensParam = searchParams.get('sensitive_attributes');
  const qis  = qiParam  ? (JSON.parse(decodeURIComponent(qiParam))  as string[]) : ctxQIs;
  const sens = sensParam ? (JSON.parse(decodeURIComponent(sensParam)) as string[]) : ctxSens;

  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('analyze');

  // Analysis
  const [analysing, setAnalysing] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState('');
  const [paretoFront, setParetoFront] = useState<number[][]>([]);

  // Plan params (autofilled from NSGA-II, editable)
  const [genStrategy, setGenStrategy] = useState('hierarchy');
  const [forceMethod, setForceMethod] = useState('');
  const [paramK, setParamK] = useState(5);
  const [paramL, setParamL] = useState(2);
  const [paramT, setParamT] = useState(0.2);
  const [paramGenLevel, setParamGenLevel] = useState(0.5);
  const [paramMaxLevel, setParamMaxLevel] = useState(4);
  const [planNote, setPlanNote] = useState('Tip: Run analysis first to auto-fill these from NSGA\u2011II.');

  // Execute
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState<ExecutionResult | null>(null);
  const [execError, setExecError] = useState('');

  // Compare
  const [comparing, setComparing] = useState(false);
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/`).then(r => setBackendOk(r.ok)).catch(() => setBackendOk(false));
  }, []);

  // ── Auto-restore previous results on mount ────────────────────────────────
  useEffect(() => {
    if (!sid) return;
    (async () => {
      // 1. Restore analysis results
      try {
        const r = await fetch(`${API_BASE}/analysis-results/${sid}`);
        if (r.ok) {
          const d = await r.json();
          if (d.has_results) {
            setAnalysis(d as AnalysisResult);
            // Restore plan params
            const op = d.optimal_parameters;
            if (op) {
              setParamK(op.k ?? 5);
              setParamL(op.l ?? 2);
              setParamT(op.t ?? 0.2);
              setParamGenLevel(op.generalization_level ?? 0.5);
              setPlanNote('Restored from previous analysis run.');
            }
            // Restore Pareto front
            const pf = d.optimization_results?.pareto_front;
            if (Array.isArray(pf)) setParetoFront(pf as number[][]);
          }
        }
      } catch { /* analysis not run yet */ }

      // 2. Restore execution results
      try {
        const r = await fetch(`${API_BASE}/execution-results/${sid}`);
        if (r.ok) {
          const d = await r.json();
          if (d.has_results) {
            setExecResult(d as ExecutionResult);
          }
        }
      } catch { /* execution not run yet */ }

      // 3. Restore comparison results (if anonymized data exists)
      try {
        const fd = new FormData();
        fd.append('session_id', sid);
        const r = await fetch(`${API_BASE}/compare`, { method: 'POST', body: fd });
        if (r.ok) {
          const d = await r.json();
          setCompareResult(d as CompareResult);
        }
      } catch { /* compare not available yet */ }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  // ── KPI values derived from latest analysis ──────────────────────────────
  const riskPct = analysis ? (analysis.risk_score * 100) : null;
  const riskPctStr = riskPct !== null ? `${riskPct.toFixed(1)}%` : '\u2014';
  const riskNote = riskPct !== null ? (riskPct > 70 ? 'High risk' : riskPct > 40 ? 'Moderate risk' : 'Lower risk') : 'Run analysis to compute';
  const minEC = analysis?.statistics?.min_equivalence_class_size;
  const uniqueRatio = analysis?.risk_metrics?.unique_records_ratio;
  const paretoCount = (() => {
    const pf = analysis?.optimization_results?.pareto_front;
    if (Array.isArray(pf)) return pf.length;
    const pfs = analysis?.optimization_results?.pareto_front_size;
    return pfs ?? null;
  })();

  // ── Handlers ─────────────────────────────────────────────────────────────

  const runAnalysis = async () => {
    if (!sid) return;
    setAnalysing(true); setAnalysisError('');
    const fd = new FormData();
    fd.append('session_id', sid);
    try {
      const res = await fetch(`${API_BASE}/analyze`, { method: 'POST', body: fd });
      if (!res.ok) throw new Error('Analysis failed');
      const data: AnalysisResult = await res.json();
      setAnalysis(data);

      // Autofill plan params from NSGA-II (already scaled to dataset size by backend)
      const op = data.optimal_parameters;
      const nRows: number = (data as unknown as Record<string, unknown>).row_count as number ?? 0;
      if (op) {
        setParamK(op.k ?? 5);
        setParamL(op.l ?? 2);
        setParamT(op.t ?? 0.2);
        setParamGenLevel(op.generalization_level ?? 0.5);
        const sizeLabel = nRows > 10_000 ? `large (${nRows.toLocaleString()} rows)`
          : nRows > 1_000 ? `medium (${nRows.toLocaleString()} rows)`
          : nRows > 0     ? `small (${nRows.toLocaleString()} rows)`
          : 'your dataset';
        setPlanNote(`Auto-filled from NSGA‑II · Scaled for ${sizeLabel} — you can still edit manually.`);
      }

      // Update Pareto chart
      const pf = data.optimization_results?.pareto_front;
      if (Array.isArray(pf)) setParetoFront(pf as number[][]);
      else setParetoFront([]);
    } catch (e: unknown) {
      setAnalysisError(e instanceof Error ? e.message : 'Analysis failed');
    } finally {
      setAnalysing(false);
    }
  };

  const runExecution = async () => {
    if (!sid) return;
    setExecuting(true); setExecError('');
    const fd = new FormData();
    fd.append('session_id', sid);
    fd.append('use_recommended', 'false');
    fd.append('anon_method', genStrategy);
    fd.append('methods', JSON.stringify({
      k: paramK,
      l: paramL,
      t: paramT,
      generalization_level: paramGenLevel,
      max_hierarchy_level: paramMaxLevel,
      forced_primary_method: forceMethod || null,
    }));
    try {
      const res = await fetch(`${API_BASE}/anonymize`, { method: 'POST', body: fd });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error((d as { detail?: string }).detail || 'Anonymization failed');
      }
      const data: ExecutionResult = await res.json();
      setExecResult(data);
    } catch (e: unknown) {
      setExecError(e instanceof Error ? e.message : 'Execution failed');
    } finally {
      setExecuting(false);
    }
  };

  const runCompare = async () => {
    if (!sid) return;
    setComparing(true);
    const fd = new FormData();
    fd.append('session_id', sid);
    try {
      const res = await fetch(`${API_BASE}/compare`, { method: 'POST', body: fd });
      if (!res.ok) throw new Error('Compare failed');
      const data: CompareResult = await res.json();
      setCompareResult(data);
    } catch { /* silent */ } finally { setComparing(false); }
  };

  const download = async (format: 'csv' | 'excel') => {
    const res = await fetch(`${API_BASE}/download-anonymized?session_id=${sid}&format=${format}`);
    if (!res.ok) { alert('Download failed'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `anonymized_data.${format === 'excel' ? 'xlsx' : 'csv'}`;
    a.click();
  };

  const proceedToReidentification = () => {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem('session_id', sid);
      if (qis.length) sessionStorage.setItem('quasi_identifiers', JSON.stringify(qis));
      if (sens.length) sessionStorage.setItem('sensitive_attributes', JSON.stringify(sens));
    }
    router.push(`/reidentification?session_id=${sid}`);
  };

  const goToTab = (tab: Tab) => setActiveTab(tab);

  const riskColorClass =
    riskPct === null ? '' :
    riskPct > 70 ? 'alert-error' :
    riskPct > 40 ? 'alert-warning' : 'alert-success';

  if (!sid) return (
    <div className="page-container">
      <div className="alert-error">No session found. <a href="/" className="underline text-blue-600 dark:text-blue-400">Go home</a></div>
    </div>
  );

  const TABS: { id: Tab; label: string }[] = [
    { id: 'analyze', label: '1) Analyze' },
    { id: 'plan',    label: '2) Plan' },
    { id: 'execute', label: '3) Execute' },
    { id: 'compare', label: '4) Compare' },
    { id: 'export',  label: '5) Export' },
  ];

  return (
    <div className="page-container">
      <Breadcrumb />

      <div className="component-header">
        <h1>Anonymization</h1>
        <p>Risk profiling \u2192 expert recommendations \u2192 NSGA\u2011II tuning \u2192 enforced anonymization \u2192 validation \u2192 export</p>
      </div>

      <StatusBadge
        status={backendOk === null ? 'checking' : backendOk ? 'connected' : 'disconnected'}
        message={backendOk === null ? 'Checking backend\u2026' : backendOk ? '\u2713 Backend connected' : '\u2717 Backend not connected'}
      />

      {/* ── Dataset + KPI Cards ─────────────────────────────────────────────── */}
      <div className="section">
        <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_0.8fr] gap-4">
          {/* Left: dataset info */}
          <div>
            <h2 className="text-lg font-semibold mb-2">Dataset</h2>
            <div className="card">
              {datasetInfo ? (
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">Session</div>
                    <div className="font-mono text-xs break-all">{sid}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">Shape</div>
                    <div><strong>{datasetInfo.shape[0]}</strong> rows \u00d7 <strong>{datasetInfo.shape[1]}</strong> columns</div>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-slate-500 dark:text-slate-400">Session: <span className="font-mono text-xs">{sid}</span></div>
              )}
            </div>

            <div className="card mt-3">
              {qis.length > 0 ? (
                <div className="text-sm">
                  <div className="text-xs text-slate-500 dark:text-slate-400">Quasi-identifiers (QI)</div>
                  <div className="font-semibold mt-1">{qis.join(', ')}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mt-2">Sensitive attributes (SI)</div>
                  <div className="mt-1">{sens.length > 0 ? <span className="font-semibold">{sens.join(', ')}</span> : <span className="text-slate-400 dark:text-slate-500">None selected</span>}</div>
                </div>
              ) : (
                <div className="alert-warning text-sm">
                  No quasi-identifiers selected.{' '}
                  <a href={`/quasi-selection?session_id=${sid}`} className="underline text-blue-600 dark:text-blue-400">Go to Quasi Selection</a>
                </div>
              )}
            </div>
          </div>

          {/* Right: KPI cards */}
          <div>
            <h2 className="text-lg font-semibold mb-2">Quick KPIs</h2>
            <div className="grid grid-cols-2 gap-3">
              <KpiCard label="Risk score" value={riskPctStr} note={riskNote} />
              <KpiCard label="Min equivalence class" value={minEC !== undefined ? String(minEC) : '\u2014'} note="Based on selected QIs" />
              <KpiCard
                label="Unique records ratio"
                value={uniqueRatio !== undefined ? `${(uniqueRatio * 100).toFixed(1)}%` : '\u2014'}
                note="Higher \u2192 higher linkage risk"
              />
              <KpiCard
                label="Pareto points"
                value={paretoCount !== null ? String(paretoCount) : '\u2014'}
                note="Disclosure risk vs utility loss"
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── Tabbed Workflow ─────────────────────────────────────────────────── */}
      <div className="section">
        {/* Tab headers */}
        <div className="flex gap-1 flex-wrap border-b border-slate-200 dark:border-slate-700 mb-4">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => goToTab(t.id)}
              className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
                activeTab === t.id
                  ? 'bg-white dark:bg-slate-800 border border-b-white dark:border-b-slate-800 border-slate-200 dark:border-slate-700 text-blue-600 dark:text-blue-400 -mb-px'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Tab: Analyze ──────────────────────────────────────────────────── */}
        {activeTab === 'analyze' && (
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <button className="btn-success" onClick={runAnalysis} disabled={analysing}>
                {analysing ? 'Analysing\u2026' : 'Run risk analysis'}
              </button>
            </div>

            {analysisError && <div className="alert-error mt-3">{analysisError}</div>}

            {analysis && (
              <div className="mt-4 space-y-4">
                <div className={`${riskColorClass} p-3 rounded`}>
                  <strong>Risk score:</strong> {riskPctStr}
                </div>

                {/* Statistics */}
                <div className="card">
                  <h3 className="font-semibold mb-2">Dataset statistics</h3>
                  <table className="w-full text-sm">
                    <tbody>
                      {[
                        ['Total records', analysis.statistics.total_records],
                        ['QI count', analysis.statistics.total_qis],
                        ['Unique QI combinations', analysis.statistics.unique_combinations],
                        ['Min equivalence class size', analysis.statistics.min_equivalence_class_size],
                        ['Avg equivalence class size', Number(analysis.statistics.avg_equivalence_class_size).toFixed(2)],
                      ].map(([k, v]) => (
                        <tr key={String(k)} className="border-b last:border-0 border-slate-100 dark:border-slate-700">
                          <td className="py-1.5 pr-4 font-medium text-slate-600 dark:text-slate-300">{k}</td>
                          <td className="py-1.5">{String(v)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Detected problems */}
                {analysis.detected_problems?.length ? (
                  <div className="alert-warning">
                    <strong>Detected issues</strong>
                    <ul className="list-disc ml-5 text-sm mt-2 space-y-1">
                      {analysis.detected_problems.map((p, i) => (
                        <li key={i}>
                          <strong>{p.problem}</strong>{' '}
                          <span className="text-xs bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300 px-1 rounded">{p.severity}</span>
                          <br />
                          <span className="text-xs text-slate-500 dark:text-slate-400">{p.condition}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {/* Triggered rules */}
                {analysis.triggered_rules?.length ? (
                  <div className="card">
                    <h3 className="font-semibold mb-2">Triggered rules</h3>
                    <ul className="list-disc ml-5 text-sm space-y-1">
                      {analysis.triggered_rules.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  </div>
                ) : null}

                {/* Expert recommendations */}
                {analysis.recommendations?.recommendations?.length ? (
                  <div className="card">
                    <h3 className="font-semibold mb-1">Expert recommendations</h3>
                    <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">
                      Primary: <strong>{analysis.recommendations.primary_method}</strong>
                      {' \u00b7 '}Hybrid: <strong>{analysis.recommendations.hybrid_approach ? 'Yes' : 'No'}</strong>
                    </div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 mb-3">
                      Overall privacy: <strong>{analysis.recommendations.overall_privacy_level}</strong>
                      {' \u00b7 '}Utility impact: <strong>{analysis.recommendations.overall_utility_impact}</strong>
                    </div>
                    <div className="space-y-2">
                      {analysis.recommendations.recommendations.slice(0, 8).map((r, i) => (
                        <div key={i} className="flex justify-between gap-3 p-3 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900">
                          <div>
                            <strong className="block text-slate-800 dark:text-slate-100">{r.method}</strong>
                            <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{r.details}</div>
                            <div className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{r.explanation}</div>
                          </div>
                          <div className="text-right shrink-0">
                            <span className="text-xs bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded">
                              {(Number(r.confidence ?? 0) * 100).toFixed(0)}%
                            </span>
                            <div className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                              Privacy {r.privacy_level} \u00b7 Utility {r.utility_impact}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {/* NSGA-II optimal params */}
                {analysis.optimal_parameters && (
                  <div className="alert-info text-sm">
                    <strong>NSGA\u2011II suggested parameters:</strong>{' '}
                    k={analysis.optimal_parameters.k}, l={analysis.optimal_parameters.l}, t={analysis.optimal_parameters.t},{' '}
                    gen={Number(analysis.optimal_parameters.generalization_level ?? 0.5).toFixed(2)}
                  </div>
                )}
              </div>
            )}

            {/* Pareto chart */}
            <div className="mt-6">
              <h3 className="font-semibold mb-1">Privacy\u2013Utility trade\u2011off</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">Each point is a candidate parameter set. Lower is better on both axes.</p>
              <ParetoChart paretoFront={paretoFront} />
            </div>
          </div>
        )}

        {/* ── Tab: Plan ─────────────────────────────────────────────────────── */}
        {activeTab === 'plan' && (
          <div>
            <h3 className="font-semibold mb-2">Recommended method plan</h3>
            {analysis?.recommendations ? (
              <div className="card mb-4">
                <div className="text-sm">
                  <div className="text-xs text-slate-500 dark:text-slate-400">Primary</div>
                  <div className="font-semibold">{analysis.recommendations.primary_method}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mt-2">Secondary</div>
                  <div>{analysis.recommendations.secondary_methods?.length ? analysis.recommendations.secondary_methods.join(', ') : <span className="text-slate-400 dark:text-slate-500">None</span>}</div>
                  {analysis.recommendations.additional_notes && (
                    <>
                      <div className="text-xs text-slate-500 dark:text-slate-400 mt-2">Notes</div>
                      <div className="text-sm">{analysis.recommendations.additional_notes}</div>
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="alert-warning text-sm mb-4">Run analysis first to generate recommendations.</div>
            )}

            <div className="card">
              <h3 className="font-semibold mb-3">Editable execution settings</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Generalization strategy</label>
                  <select
                    value={genStrategy}
                    onChange={e => setGenStrategy(e.target.value)}
                    className="border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded p-2 w-full text-sm"
                  >
                    <option value="hierarchy">Hierarchy-based (recommended)</option>
                    <option value="traditional">Traditional (fallback)</option>
                  </select>
                  <div className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                    Hierarchy uses detected attribute types and Sri Lanka admin templates when available.
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Force primary method (optional)</label>
                  <select
                    value={forceMethod}
                    onChange={e => setForceMethod(e.target.value)}
                    className="border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded p-2 w-full text-sm"
                  >
                    <option value="">Use expert-system primary method</option>
                    <option value="k_anonymity">Force K-Anonymity</option>
                    <option value="l_diversity">Force L-Diversity</option>
                    <option value="t_closeness">Force T-Closeness</option>
                    <option value="pram">Force PRAM (Categorical Perturbation)</option>
                    <option value="hybrid">Force Hybrid</option>
                  </select>
                  <div className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                    Lets you override the recommendation for experimentation.
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 mt-4">
                {[
                  { label: 'k', val: paramK, set: setParamK, min: 2, max: 50, step: 1 },
                  { label: 'l', val: paramL, set: setParamL, min: 2, max: 10, step: 1 },
                  { label: 't', val: paramT, set: setParamT, min: 0.01, max: 0.5, step: 0.01 },
                ].map(({ label, val, set, min, max, step }) => (
                  <div key={label}>
                    <label className="block text-sm font-medium mb-1">{label}</label>
                    <input
                      type="number" value={val} min={min} max={max} step={step}
                      onChange={e => set(parseFloat(e.target.value))}
                      className="border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded p-2 w-full text-sm"
                    />
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-4 mt-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Generalization level <span className="text-xs text-slate-400">(0..1)</span></label>
                  <input
                    type="number" value={paramGenLevel} min={0} max={1} step={0.05}
                    onChange={e => setParamGenLevel(parseFloat(e.target.value))}
                    className="border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded p-2 w-full text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Max hierarchy level</label>
                  <input
                    type="number" value={paramMaxLevel} min={1} max={6} step={1}
                    onChange={e => setParamMaxLevel(parseInt(e.target.value))}
                    className="border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded p-2 w-full text-sm"
                  />
                </div>
              </div>

              <div className="text-xs text-slate-400 dark:text-slate-500 mt-3">{planNote}</div>
            </div>
          </div>
        )}

        {/* ── Tab: Execute ──────────────────────────────────────────────────── */}
        {activeTab === 'execute' && (
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <button className="btn-success" onClick={runExecution} disabled={executing}>
                {executing ? 'Executing\u2026' : 'Execute anonymization (enforced + validated)'}
              </button>
            </div>

            {execError && <div className="alert-error mt-3">{execError}</div>}

            {execResult && (
              <div className="mt-4 space-y-4">
                <div className="alert-success">Execution complete</div>

                <div className="card">
                  <h3 className="font-semibold mb-3">Result</h3>
                  <div className="grid grid-cols-3 gap-3">
                    <KpiCard label="Suppression ratio" value={`${(execResult.metrics.suppression_ratio * 100).toFixed(1)}%`} />
                    <KpiCard label="Min equivalence class" value={String(execResult.metrics.min_equivalence_class_size)} />
                    <KpiCard label="Avg equivalence class" value={String(execResult.metrics.avg_equivalence_class_size ?? '\u2014')} />
                  </div>
                  {execResult.applied_methods?.length ? (
                    <div className="text-xs text-slate-400 dark:text-slate-500 mt-3">
                      Applied: {execResult.applied_methods.join(', ')}
                    </div>
                  ) : null}
                </div>

                {/* Constraint validation */}
                {execResult.validation && Object.keys(execResult.validation).length > 0 && (() => {
                  const keys = Object.keys(execResult.validation!);
                  const allValid = keys.every(k => execResult.validation![k].is_valid);
                  return (
                    <>
                      {allValid
                        ? <div className="alert-success">All constraints satisfied</div>
                        : <div className="alert-warning">Some constraints not fully satisfied</div>
                      }
                      <div className="card">
                        <h3 className="font-semibold mb-3">Constraint validation</h3>
                        <div className="space-y-2">
                          {keys.map(k => {
                            const v = execResult.validation![k];
                            return (
                              <div key={k} className="flex justify-between gap-3 p-3 border border-slate-200 dark:border-slate-700 rounded-lg">
                                <div>
                                  <strong className="block text-sm">{k}</strong>
                                  <div className="text-xs text-slate-400 dark:text-slate-500">{v.message}</div>
                                </div>
                                <div className="text-right shrink-0">
                                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${v.is_valid ? 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300' : 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300'}`}>
                                    {v.is_valid ? 'PASS' : 'FAIL'}
                                  </span>
                                  <div className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                                    Actual {v.actual_value} · Required {v.required_value}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </>
                  );
                })()}

                {/* Preview */}
                {execResult.sample_data?.length ? (
                  <div className="card">
                    <h3 className="font-semibold mb-2">Preview (first 5 rows)</h3>
                    <DataTable columns={execResult.columns ?? []} rows={execResult.sample_data} maxRows={5} />
                  </div>
                ) : null}
              </div>
            )}
          </div>
        )}

        {/* ── Tab: Compare ──────────────────────────────────────────────────── */}
        {activeTab === 'compare' && (
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <button className="btn-primary" onClick={runCompare} disabled={comparing}>
                {comparing ? 'Generating\u2026' : 'Generate comparison report'}
              </button>
            </div>

            {compareResult && (
              <div className="mt-4 space-y-4">
                <div className="alert-success">Comparison report generated</div>

                <div className="alert-info text-sm">
                  <h3 className="font-semibold mb-1">Dataset overview</h3>
                  <p><strong>Original:</strong> {compareResult.original_shape[0]} rows \u00d7 {compareResult.original_shape[1]} columns</p>
                  <p><strong>Anonymized:</strong> {compareResult.anonymized_shape[0]} rows \u00d7 {compareResult.anonymized_shape[1]} columns</p>
                </div>

{compareResult.statistics_comparison && (
                  <div className="alert-warning text-sm">
                    <h3 className="font-semibold mb-1">QI changes</h3>
                    {compareResult.statistics_comparison.original_unique_qi_combinations !== undefined && (
                      <p><strong>Original unique QI combinations:</strong> {compareResult.statistics_comparison.original_unique_qi_combinations}</p>
                    )}
                    {compareResult.statistics_comparison.anonymized_unique_qi_combinations !== undefined && (
                      <p><strong>Anonymized unique QI combinations:</strong> {compareResult.statistics_comparison.anonymized_unique_qi_combinations}</p>
                    )}
                    <p><strong>Combination reduction:</strong> {compareResult.statistics_comparison.combination_reduction.toFixed(1)}%</p>
                    <p>
                      <strong>Modified rows:</strong> {compareResult.statistics_comparison.modified_qi_rows} of {compareResult.original_shape[0]}{' '}
                      ({((compareResult.statistics_comparison.modified_qi_rows / compareResult.original_shape[0]) * 100).toFixed(1)}%)
                    </p>
                    {compareResult.statistics_comparison.suppressed_qi_cells !== undefined && (
                      <p>
                        <strong>Suppressed QI values:</strong> {compareResult.statistics_comparison.suppressed_qi_cells} of {compareResult.statistics_comparison.total_qi_cells}{' '}
                        ({compareResult.statistics_comparison.total_qi_cells ? ((compareResult.statistics_comparison.suppressed_qi_cells / compareResult.statistics_comparison.total_qi_cells) * 100).toFixed(1) : 0}%)
                      </p>
                    )}
                  </div>
                )}

                {/* Risk comparison metrics */}
                {compareResult.risk_comparison && compareResult.risk_comparison.pre_risk_metrics && compareResult.risk_comparison.post_risk_metrics && (
                  <div className="card">
                    <h3 className="font-semibold mb-3">Risk Metrics Comparison (Pre vs Post Anonymization)</h3>
                    
                    {/* Risk metrics table */}
                    <table className="w-full text-sm border-collapse mb-4">
                      <thead>
                        <tr className="bg-green-600 dark:bg-green-800 text-white">
                          <th className="px-3 py-2 text-left border border-green-500 dark:border-green-700">Metric</th>
                          <th className="px-3 py-2 text-center border border-green-500 dark:border-green-700">Before (Original)</th>
                          <th className="px-3 py-2 text-center border border-green-500 dark:border-green-700">After (Anonymized)</th>
                          <th className="px-3 py-2 text-center border border-green-500 dark:border-green-700">Change</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          { label: 'Prosecutor Risk', pre: compareResult.risk_comparison.pre_risk_metrics?.prosecutor_risk, post: compareResult.risk_comparison.post_risk_metrics?.prosecutor_risk },
                          { label: 'Journalist Risk', pre: compareResult.risk_comparison.pre_risk_metrics?.journalist_risk, post: compareResult.risk_comparison.post_risk_metrics?.journalist_risk },
                          { label: 'Linkage Risk', pre: compareResult.risk_comparison.pre_risk_metrics?.linkage_risk, post: compareResult.risk_comparison.post_risk_metrics?.linkage_risk },
                          { label: 'Unique Records Ratio', pre: compareResult.risk_comparison.pre_risk_metrics?.unique_records_ratio, post: compareResult.risk_comparison.post_risk_metrics?.unique_records_ratio, isPercent: true },
                          { label: 'Min Equivalence Class', pre: compareResult.risk_comparison.pre_risk_metrics?.min_group_size, post: compareResult.risk_comparison.post_risk_metrics?.min_group_size },
                          { label: 'Avg Equivalence Class', pre: compareResult.risk_comparison.pre_risk_metrics?.avg_group_size, post: compareResult.risk_comparison.post_risk_metrics?.avg_group_size },
                        ].map((row, i) => {
                          const preVal = row.pre ?? 0;
                          const postVal = row.post ?? 0;
                          const change = row.isPercent 
                            ? ((preVal - postVal) * 100).toFixed(1) + '%'
                            : (preVal - postVal).toFixed(3);
                          const isImprovement = preVal > postVal;
                          
                          return (
                            <tr key={i} className="border-b border-slate-200 dark:border-slate-700">
                              <td className="px-3 py-2 font-medium">{row.label}</td>
                              <td className="px-3 py-2 text-center">
                                {row.isPercent ? `${(preVal * 100).toFixed(1)}%` : typeof preVal === 'number' ? preVal.toFixed(3) : preVal}
                              </td>
                              <td className="px-3 py-2 text-center">
                                {row.isPercent ? `${(postVal * 100).toFixed(1)}%` : typeof postVal === 'number' ? postVal.toFixed(3) : postVal}
                              </td>
                              <td className={`px-3 py-2 text-center font-bold ${isImprovement ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                {isImprovement ? '↓' : '↑'} {change}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>

                    {/* Risk improvement summary */}
                    {compareResult.risk_comparison.improvement && (
                      <div className="mt-4 p-3 bg-green-50 dark:bg-green-950 rounded-lg border border-green-200 dark:border-green-800">
                        <h4 className="font-semibold text-green-800 dark:text-green-200 mb-2">Risk Reduction Summary</h4>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                          {compareResult.risk_comparison.improvement.prosecutor_risk_reduction !== undefined && (
                            <div className="text-center">
                              <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                                {(compareResult.risk_comparison.improvement.prosecutor_risk_reduction * 100).toFixed(1)}%
                              </div>
                              <div className="text-xs text-slate-500 dark:text-slate-400">Prosecutor Risk</div>
                            </div>
                          )}
                          {compareResult.risk_comparison.improvement.journalist_risk_reduction !== undefined && (
                            <div className="text-center">
                              <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                                {(compareResult.risk_comparison.improvement.journalist_risk_reduction * 100).toFixed(1)}%
                              </div>
                              <div className="text-xs text-slate-500 dark:text-slate-400">Journalist Risk</div>
                            </div>
                          )}
                          {compareResult.risk_comparison.improvement.unique_records_reduction !== undefined && (
                            <div className="text-center">
                              <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                                {(compareResult.risk_comparison.improvement.unique_records_reduction * 100).toFixed(1)}%
                              </div>
                              <div className="text-xs text-slate-500 dark:text-slate-400">Unique Records</div>
                            </div>
                          )}
                          {compareResult.risk_comparison.improvement.overall_risk_reduction !== undefined && (
                            <div className="text-center">
                              <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                                {(compareResult.risk_comparison.improvement.overall_risk_reduction * 100).toFixed(1)}%
                              </div>
                              <div className="text-xs text-slate-500 dark:text-slate-400">Overall Risk</div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Column comparison table */}
                {compareResult.column_comparison?.length ? (
                  <div className="card overflow-x-auto">
                    <h3 className="font-semibold mb-3">Column-by-column comparison</h3>
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="bg-blue-600 dark:bg-blue-800 text-white">
                          {['Column', 'QI', 'Orig Unique', 'Anon Unique', 'Suppressed', 'Changed'].map(h => (
                            <th key={h} className="px-3 py-2 text-left border border-blue-500 dark:border-blue-700">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {compareResult.column_comparison.map((col, i) => (
                          <tr key={i} className={col.changes_detected ? 'bg-red-50 dark:bg-red-950' : 'bg-green-50 dark:bg-green-950'}>
                            <td className="px-3 py-2 border border-slate-200 dark:border-slate-700 font-medium">{col.column_name}</td>
                            <td className="px-3 py-2 border border-slate-200 dark:border-slate-700 text-center font-bold">{col.is_quasi_identifier ? '\u2713 QI' : '-'}</td>
                            <td className="px-3 py-2 border border-slate-200 dark:border-slate-700 text-center">{col.original_unique}</td>
                            <td className="px-3 py-2 border border-slate-200 dark:border-slate-700 text-center">{col.anonymized_unique}</td>
                            <td className="px-3 py-2 border border-slate-200 dark:border-slate-700 text-center">
                              {(col.suppressed_values ?? 0) > 0
                                ? <span className="bg-red-500 text-white px-2 py-0.5 rounded text-xs">{col.suppressed_values}</span>
                                : '0'}
                            </td>
                            <td className="px-3 py-2 border border-slate-200 dark:border-slate-700 text-center">
                              {(col.changed_values ?? 0) > 0
                                ? <span className="bg-orange-400 text-white px-2 py-0.5 rounded text-xs">{col.changed_values}</span>
                                : '0'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}

                {/* Sample comparison */}
                {compareResult.sample_comparison?.slice(0, 5).map((row, idx) => (
                  <div key={idx} className="card">
                    <h4 className="font-semibold mb-3">Row {idx + 1}</h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <h5 className="text-sm font-medium text-blue-600 dark:text-blue-400 mb-2">Original</h5>
                        {Object.entries(row.original).map(([col, val]) => {
                          const isQI = compareResult.quasi_identifiers?.includes(col);
                          const isChanged = row.differences.includes(col);
                          return (
                            <div key={col} className={`text-sm px-2 py-1 mb-1 rounded border-l-2 ${isChanged ? 'bg-amber-50 dark:bg-amber-950' : ''} ${isQI ? 'border-blue-500' : 'border-transparent'}`}>
                              <strong>{col}:</strong> {String(val ?? '(null)')}
                            </div>
                          );
                        })}
                      </div>
                      <div>
                        <h5 className="text-sm font-medium text-purple-600 dark:text-purple-400 mb-2">Anonymized</h5>
                        {Object.entries(row.anonymized).map(([col, val]) => {
                          const isQI = compareResult.quasi_identifiers?.includes(col);
                          const isChanged = row.differences.includes(col);
                          return (
                            <div key={col} className={`text-sm px-2 py-1 mb-1 rounded border-l-2 ${isChanged ? 'bg-red-50 dark:bg-red-950' : ''} ${isQI ? 'border-purple-500' : 'border-transparent'}`}>
                              <strong>{col}:</strong> {String(val ?? '(null)')}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    {row.differences.length > 0 && (
                      <p className="text-xs text-red-500 dark:text-red-400 mt-2">Changed columns: {row.differences.join(', ')}</p>
                    )}
                  </div>
                ))}

                <button className="btn-success" onClick={() => goToTab('export')}>
                  Download Anonymized Data \u2192
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── Tab: Export ───────────────────────────────────────────────────── */}
        {activeTab === 'export' && (
          <div className="space-y-4">
            <h3 className="font-semibold">Download anonymized dataset</h3>
            <div className="flex gap-3 flex-wrap">
              <button className="btn-success" onClick={() => download('csv')}>Download CSV</button>
              <button className="btn-info" onClick={() => download('excel')}>Download Excel</button>
            </div>
            <div className="text-xs text-slate-400 dark:text-slate-500">
              Exports the latest anonymized dataset stored in the backend session.
            </div>

            <div className="card mt-4">
              <h3 className="font-semibold mb-2">Proceed to Re-identification Check</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">
                After downloading, verify the anonymized data and check for potential re-identification risks.
              </p>
              <button className="btn-primary" onClick={proceedToReidentification}>
                Check Re-identification Risk \u2192
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Navigation ──────────────────────────────────────────────────────── */}
      <div className="section">
        <h3>Other Components</h3>
        <div className="flex gap-3 flex-wrap mt-2">
          <button className="btn-secondary" onClick={() => router.push(`/quasi-selection?session_id=${sid}`)}>Back to Quasi Selection</button>
          <button className="btn-secondary" onClick={() => router.push('/')}>Back to Home</button>
        </div>
      </div>
    </div>
  );
}

export default function AnonymizationPage() {
  return (
    <Suspense fallback={<div className="page-container"><p>Loading…</p></div>}>
      <AnonymizationInner />
    </Suspense>
  );
}
