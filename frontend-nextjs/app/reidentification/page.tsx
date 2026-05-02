'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useSession, API_BASE } from '@/lib/SessionContext';
import Breadcrumb from '@/components/Breadcrumb';
import StatusBadge from '@/components/StatusBadge';
import DataTable from '@/components/DataTable';

// Pipeline step definitions (mirrors Streamlit pipeline — internal risk & aggregation skipped)
const PIPELINE_STEPS = [
  { id: 'st1', label: 'Data Inspection',      agent: 'Agent 1' },
  { id: 'st2', label: 'Validate Identifiers', agent: 'Agent 2' },
  { id: 'st3', label: 'Generate Pairs',       agent: 'Agent 3' },
  { id: 'st4', label: 'ML Attack',            agent: 'Agent 4' },
  { id: 'st5', label: 'Score Risk',           agent: 'Agent 5' },
  { id: 'st6', label: 'SHAP Explain',         agent: 'Agent 5c' },
  { id: 'st7', label: 'LLM Explain',          agent: 'Agent 7' },
];

type StepStatus = 'pending' | 'running' | 'done' | 'error' | 'skip';

// Risk score column priority — mirrors Streamlit's load_final_risk() detection
const RISK_COL_PRIORITY = ['max_attack_score', 'ml_attack_risk', 'final_risk_score_0_1'];

function detectRiskCol(columns: string[]): string {
  for (const col of RISK_COL_PRIORITY) {
    if (columns.includes(col)) return col;
  }
  return columns.find(c => !['anon_id', 'record_id', 'pair_index', 'label'].includes(c)) ?? 'risk_score';
}

function normalizeCompareValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  return String(value).trim().toLowerCase();
}

function valuesMatch(auxValue: unknown, anonValue: unknown): boolean {
  return normalizeCompareValue(auxValue) === normalizeCompareValue(anonValue);
}

function bothValuesEmpty(auxValue: unknown, anonValue: unknown): boolean {
  return normalizeCompareValue(auxValue) === '' && normalizeCompareValue(anonValue) === '';
}

function isNumericValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return false;
  return !Number.isNaN(Number(value));
}

function compareStatus(auxValue: unknown, anonValue: unknown): 'match' | 'close' | 'changed' | 'missing' {
  if (bothValuesEmpty(auxValue, anonValue)) return 'missing';
  if (valuesMatch(auxValue, anonValue)) return 'match';
  if (isNumericValue(auxValue) && isNumericValue(anonValue)) {
    const auxNum = Number(auxValue);
    const anonNum = Number(anonValue);
    if (auxNum === anonNum) return 'match';  // 10 === 10.0
    const delta = Math.abs(auxNum - anonNum);
    if (delta <= 1) return 'close';
  }
  return 'changed';
}

function riskLevelFromAttackScore(score?: number): 'High' | 'Medium' | 'Low' {
  if (score == null || Number.isNaN(score)) return 'Low';
  if (score >= 0.7) return 'High';
  if (score >= 0.4) return 'Medium';
  return 'Low';
}

interface RiskRecord {
  anon_id?: string | number;
  record_id?: string | number;
  [key: string]: unknown;
}

interface ShapFeature {
  feature: string;
  mean_abs_shap?: number;
  importance?: number;
  [key: string]: unknown;
}

interface VulnerableColumn {
  columnName: string;
  score: number;
}

interface PipelineResult {
  overall_risk_score?: number;
  total_records?: number;
  high_risk_count?: number;
  matched_count?: number;
  risk_records?: RiskRecord[];
  risk_col?: string;
  shap_features?: ShapFeature[];
  vulnerable_columns?: VulnerableColumn[];
  columns?: string[];
  // Percentile thresholds
  p95?: number;
  p80?: number;
  p50?: number;
  critical_count?: number;
  medium_count?: number;
  low_count?: number;
}

interface MatchedRowPair {
  aux_index: number;
  anon_index: number;
  overall_similarity?: number;
  attack_score?: number;
  auxiliary_row: Record<string, unknown>;
  anonymized_row: Record<string, unknown>;
}

interface InspectionResult {
  data_profile?: {
    dataset_overview?: {
      total_rows: number;
      total_columns: number;
      total_cells: number;
      memory_usage_mb: number;
      duplicate_rows: number;
      duplicate_percentage: number;
    };
    data_quality?: {
      completeness_percentage: number;
      total_null_cells: number;
      total_null_percentage: number;
      columns_with_nulls: number;
      columns_fully_null: number;
    };
    statistical_summary?: {
      numeric_columns_count: number;
      categorical_columns_count: number;
      datetime_columns_count: number;
    };
    column_profiles?: Record<string, {
      data_type: string;
      null_percentage: number;
      unique_count: number;
      unique_percentage: number;
    }>;
  };
  schema_validation?: {
    total_columns: number;
    total_rows: number;
    validation_passed: boolean;
    issues_found: number;
    duplicate_columns: string[];
    empty_columns: string[];
    constant_columns: string[];
    high_null_columns: { column: string; null_rate: number }[];
  };
  missing_value_report?: {
    missing_summary: {
      total_missing: number;
      total_cells: number;
      overall_missing_rate: number;
      columns_with_missing: number;
    };
    column_analysis: Record<string, { missing_count: number; missing_rate: number; dtype: string }>;
  };
  anomaly_report?: {
    anomalies: {
      column: string;
      type: string;
      count?: number;
      percentage?: number;
      unique_count?: number;
      unique_ratio?: number;
      note?: string;
    }[];
    total_anomalies: number;
  };
  merged_dataset_shape?: [number, number];
}

type ActiveTab = 'summary' | 'records' | 'vulnerability' | 'shap' | 'llm';

// ─── LLM Tab: auto-loads existing results, displays without controls ───────
type LlmExplanation = { record_id: string; risk_score?: number; explanation: string };
type LlmData = { summary?: string; explanations?: LlmExplanation[] } | null;

function LlmTabAutoLoader({
  sid, llmResult, setLlmResult, selectedLlmIdx, setSelectedLlmIdx,
}: {
  sid: string;
  llmResult: LlmData;
  setLlmResult: (v: LlmData) => void;
  selectedLlmIdx: number;
  setSelectedLlmIdx: (i: number) => void;
}) {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/results/llm-explanations/${sid}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setSelectedLlmIdx(0);
          setLlmResult({ summary: d.dataset_summary, explanations: d.explanations });
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  if (loading) return <div className="mt-6 flex items-center justify-center p-8 bg-slate-900/30 rounded-xl border border-slate-800 animate-pulse"><p className="text-slate-400">⏳ Loading AI Explanations…</p></div>;
  if (!llmResult) return <div className="mt-6 p-6 bg-slate-900/30 border border-slate-800 rounded-xl"><p className="text-slate-500 text-center">ℹ️ No AI Explanations available yet. Run the pipeline first — explanations are generated automatically.</p></div>;

  return (
    <div className="mt-4 space-y-6">
      {/* Dataset Summary */}
      {llmResult.summary && (
        <div className="bg-slate-900/50 border border-slate-700/50 rounded-2xl p-6 shadow-inner">
          <h3 className="text-xl font-bold text-slate-100 flex items-center gap-2 mb-4">
            <span className="text-purple-400">📊</span> Dataset Risk Summary
          </h3>
          <div className="bg-slate-950/50 border-l-4 border-purple-500 rounded-r-lg p-5 text-sm whitespace-pre-wrap font-mono leading-relaxed text-slate-300 shadow-sm">
            {llmResult.summary}
          </div>
        </div>
      )}

      {llmResult.explanations?.length ? (
        <div className="bg-slate-900/30 border border-slate-700/50 p-6 rounded-2xl">
          <h3 className="text-xl font-bold text-slate-100 flex items-center gap-2 mb-5">
            <span className="text-blue-400">🤖</span> Individual Record Explanations
          </h3>

          {/* Record Selector */}
          <div className="mb-6">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2 block">Select a record to view explanation:</label>
            <div className="relative">
              <select
                className="w-full appearance-none bg-slate-800 border border-slate-600 text-slate-200 rounded-lg p-3 pr-10 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors shadow-sm cursor-pointer"
                value={selectedLlmIdx}
                onChange={e => setSelectedLlmIdx(Number(e.target.value))}
              >
                {llmResult.explanations.map((exp, i) => {
                  const rs = exp.risk_score ?? 0;
                  const icon = rs >= 0.7 ? '🔴' : rs >= 0.3 ? '🟡' : '🟢';
                  return (
                    <option key={exp.record_id} value={i} className="bg-slate-800 text-slate-200">
                      Record {exp.record_id} — Risk: {rs.toFixed(4)} {icon}
                    </option>
                  );
                })}
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-slate-400">
                ▼
              </div>
            </div>
          </div>

          {/* Selected record detail */}
          {(() => {
            const exp = llmResult.explanations![selectedLlmIdx];
            if (!exp) return null;
            const rs = exp.risk_score ?? 0;
            const cat = rs >= 0.7 ? 'HIGH' : rs >= 0.3 ? 'MEDIUM' : 'LOW';
            
            // Premium styling based on risk level
            const theme = cat === 'HIGH' 
              ? { icon: '🔴', cardBg: 'bg-red-900/10 border-red-800/50', valColor: 'text-red-400', expBg: 'bg-red-950/40 border-l-red-500 text-red-200', label: 'bg-red-500/20 text-red-300 border-red-500/30' }
              : cat === 'MEDIUM' 
                ? { icon: '🟡', cardBg: 'bg-yellow-900/10 border-yellow-800/50', valColor: 'text-yellow-400', expBg: 'bg-yellow-950/40 border-l-yellow-500 text-yellow-200', label: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' }
                : { icon: '🟢', cardBg: 'bg-emerald-900/10 border-emerald-800/50', valColor: 'text-emerald-400', expBg: 'bg-emerald-950/40 border-l-emerald-500 text-emerald-200', label: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' };

            return (
              <div className="mt-4 bg-slate-800/40 border border-slate-700/50 rounded-xl p-5">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
                  <div className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-black text-slate-200">{exp.record_id}</div>
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-500 mt-1">Record ID</div>
                  </div>
                  <div className={`bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 text-center`}>
                    <div className={`text-2xl font-black ${theme.valColor}`}>{rs.toFixed(4)}</div>
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-500 mt-1">Risk Score</div>
                  </div>
                  <div className={`bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 flex flex-col items-center justify-center`}>
                    <div className={`px-3 py-1 rounded border ${theme.label} font-bold text-sm flex items-center gap-2`}>
                      {theme.icon} {cat}
                    </div>
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-500 mt-2">Risk Level</div>
                  </div>
                </div>
                
                <div>
                  <h5 className="text-sm font-bold text-slate-300 flex items-center gap-2 mb-3">
                    <span className="text-purple-400">✨</span> AI-Generated Explanation
                  </h5>
                  <div className={`p-5 rounded-r-xl border border-y-slate-700/30 border-r-slate-700/30 border-l-4 text-sm leading-relaxed ${theme.expBg} shadow-inner`}>
                    {exp.explanation}
                  </div>
                </div>
              </div>
            );
          })()}

          {/* All records collapsible */}
          <details className="mt-6 group">
            <summary className="cursor-pointer text-sm font-medium text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-2 select-none outline-none">
              <span className="bg-blue-500/10 p-1.5 rounded-md group-open:rotate-90 transition-transform">▶</span>
              📚 View All {llmResult.explanations.length} Explained Records
            </summary>
            <div className="mt-4 space-y-3 pl-2">
              {llmResult.explanations.map((exp, i) => {
                const rs = exp.risk_score ?? 0;
                const cat = rs >= 0.7 ? 'HIGH' : rs >= 0.3 ? 'MEDIUM' : 'LOW';
                const theme = cat === 'HIGH' ? { icon: '🔴', border: 'border-l-red-500', text: 'text-red-400' } : cat === 'MEDIUM' ? { icon: '🟡', border: 'border-l-yellow-500', text: 'text-yellow-400' } : { icon: '🟢', border: 'border-l-emerald-500', text: 'text-emerald-400' };
                
                return (
                  <div key={exp.record_id} className={`bg-slate-800/40 border border-slate-700/50 border-l-4 ${theme.border} rounded-lg p-4 hover:bg-slate-800/80 transition-colors`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="font-bold text-slate-200 flex items-center gap-2">
                        {theme.icon} Record {exp.record_id}
                      </div>
                      <div className={`text-xs font-bold ${theme.text}`}>
                        Risk: {rs.toFixed(4)}
                      </div>
                    </div>
                    <p className="text-slate-400 text-sm leading-relaxed">
                      {exp.explanation.slice(0, 180)}…
                      <button className="ml-2 text-blue-400 hover:text-blue-300 font-semibold underline decoration-blue-400/30 underline-offset-2" onClick={(e) => {
                        e.preventDefault();
                        setSelectedLlmIdx(i);
                        // Using a small hack to scroll the details component into view
                        e.currentTarget.closest('details')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                      }}>Read full</button>
                    </p>
                  </div>
                );
              })}
            </div>
          </details>
        </div>
      ) : (
        <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-6 text-center">
          <p className="text-slate-500">No individual explanations found in results.</p>
        </div>
      )}
    </div>
  );
}

// ─── Aggregate engineered SHAP features back to original column names ──────────
// e.g. age_diff + age_equal → "age"  |  euclidean_distance → "Overall Similarity"
const ENGINEERED_SUFFIXES = ['_diff', '_equal', '_ratio', '_match', '_score'];
const GLOBAL_KEYWORDS = ['euclidean', 'manhattan', 'cosine', 'jaccard', 'hamming', 'distance', 'similarity', 'overall'];

function aggregateShapFeatures(features: ShapFeature[]): { col: string; avgImportance: number; maxImportance: number; rawFeatures: string[] }[] {
  const grouped: Record<string, { sum: number; max: number; count: number; raw: string[] }> = {};

  for (const f of features) {
    const imp = f.importance ?? 0;
    const name = f.feature.toLowerCase();

    // Global distance/similarity metrics → group under one label
    let colKey: string;
    if (GLOBAL_KEYWORDS.some(k => name.includes(k))) {
      colKey = 'Overall Similarity';
    } else {
      // Strip engineered suffix to get original column name
      const matched = ENGINEERED_SUFFIXES.find(s => f.feature.endsWith(s));
      colKey = matched ? f.feature.slice(0, -matched.length) : f.feature;
    }

    if (!grouped[colKey]) grouped[colKey] = { sum: 0, max: 0, count: 0, raw: [] };
    grouped[colKey].sum += imp;
    grouped[colKey].max = Math.max(grouped[colKey].max, imp);
    grouped[colKey].count++;
    grouped[colKey].raw.push(f.feature);
  }

  return Object.entries(grouped)
    .map(([col, g]) => ({ col, avgImportance: g.sum / g.count, maxImportance: g.max, rawFeatures: g.raw }))
    .sort((a, b) => b.avgImportance - a.avgImportance);
}

/* ── Semi-circular gauge ─────────────────────────────────────── */
function SemiGauge({ value, label }: { value: number; label: string }) {
  const cx = 60, cy = 58, r = 46;
  const v = Math.max(0, Math.min(100, value));

  // Angle mapping: 0% → 180°, 50% → 270° (top), 100% → 360°/0°
  // i.e. θ_deg = 180 + pct * 1.8
  function pt(pct: number): [number, number] {
    const deg = 180 + pct * 1.8;
    const rad = (deg * Math.PI) / 180;
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
  }

  function arcPath(fromPct: number, toPct: number): string {
    const [x1, y1] = pt(fromPct);
    const [x2, y2] = pt(toPct);
    const span = (toPct - fromPct) * 1.8;
    const large = span > 180 ? 1 : 0;
    return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
  }

  const [p0x, p0y]   = pt(0);
  const [p50x, p50y] = pt(50);
  const [p100x, p100y] = pt(100);

  // Modern gauge styling
  let strokeColor = "#22c55e"; // green
  if (v >= 40) strokeColor = "#eab308"; // yellow
  if (v >= 70) strokeColor = "#ef4444"; // red

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 120 72" width="130" height="78" className="drop-shadow-sm">
        {/* Background track (darker/faint) */}
        <path d={arcPath(0, 100)} fill="none" stroke="#1e293b" strokeWidth="12" strokeLinecap="round" />
        
        {/* Value track (colored, matching the risk level) */}
        {v > 0 && (
          <path d={arcPath(0, v)} fill="none" stroke={strokeColor} strokeWidth="12" strokeLinecap="round" 
                style={{ filter: `drop-shadow(0 0 4px ${strokeColor}60)` }} />
        )}
        
        {/* Tick labels */}
        <text x={p0x - 8}  y={p0y + 8}   fontSize="8" fontWeight="600" fill="#64748b" textAnchor="middle">0</text>
        <text x={p50x}     y={p50y - 12} fontSize="8" fontWeight="600" fill="#64748b" textAnchor="middle">50</text>
        <text x={p100x + 8} y={p100y + 8} fontSize="8" fontWeight="600" fill="#64748b" textAnchor="middle">100</text>
        
        {/* Value text in center */}
        <text x={cx} y={cy + 8} fontSize="20" fontWeight="800" fill={strokeColor} textAnchor="middle">{v.toFixed(1)}</text>
      </svg>
      <div className="text-xs text-slate-400 font-medium text-center leading-tight mt-1" style={{ maxWidth: 130 }}>{label}</div>
    </div>
  );
}

function ReidentificationInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { sessionId: ctxSid, quasiIdentifiers: ctxQIs, datasetInfo } = useSession();

  const sid = searchParams.get('session_id') || ctxSid || '';
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  // Dataset preview
  const [previewCols, setPreviewCols] = useState<string[]>([]);
  const [previewRows, setPreviewRows] = useState<Record<string, unknown>[]>([]);

  // QI chips
  const [allCols, setAllCols] = useState<string[]>(datasetInfo?.columns ?? []);
  const [selectedQIs, setSelectedQIs] = useState<Set<string>>(new Set(ctxQIs));

  // Auxiliary upload
  const auxInputRef = useRef<HTMLInputElement>(null);
  const [auxStatus, setAuxStatus] = useState<{
    has_custom_auxiliary: boolean;
    auxiliary_filename?: string;
    auxiliary_rows?: number;
    anonymized_rows?: number;
  } | null>(null);

  // Pipeline config
  const [attackMode, setAttackMode] = useState('external');
  const [strength, setStrength] = useState('strong');
  const [models, setModels] = useState({ logreg: true, rf: true, gbm: true, xgb: true });

  // Pipeline run
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState('');
  const [running, setRunning] = useState(false);
  const [applyingVulnCols, setApplyingVulnCols] = useState(false);

  // Results
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>('summary');
  const [riskThreshold, setRiskThreshold] = useState(0.5);

  // Warnings
  const [noAnonWarning, setNoAnonWarning] = useState(false);

  // SHAP local top features map: anon_id → "feat1, feat2, feat3"
  const [shapTopFeatures, setShapTopFeatures] = useState<Record<string, string>>({});

  // Matched auxiliary <-> anonymized row comparisons
  const [matchedPairs, setMatchedPairs] = useState<MatchedRowPair[]>([]);
  const [selectedPairIdx, setSelectedPairIdx] = useState(0);
  const [matchedPairsMessage, setMatchedPairsMessage] = useState('');
  const [showFullPairData, setShowFullPairData] = useState(false);

  // LLM
  const [llmResult, setLlmResult] = useState<LlmData>(null);
  const [selectedLlmIdx, setSelectedLlmIdx] = useState(0);

  // Agent 1 inspection dashboard
  const [inspectionResult, setInspectionResult] = useState<InspectionResult | null>(null);

  // True total anonymized record count (from /compare endpoint)
  const [totalAnonRows, setTotalAnonRows] = useState<number>(0);

  useEffect(() => {
    fetch(`${API_BASE}/`).then(r => setBackendOk(r.ok)).catch(() => setBackendOk(false));
  }, []);

  // Initial page load
  useEffect(() => {
    if (!sid) return;
    (async () => {
      // Load session columns
      try {
        const r = await fetch(`${API_BASE}/session/${sid}`);
        if (r.ok) {
          const d = await r.json();
          setAllCols(d.columns ?? []);
          if (d.quasi_identifiers?.length) setSelectedQIs(new Set(d.quasi_identifiers));
          if (d.has_anonymized_data === false) setNoAnonWarning(true);
        }
      } catch {}

      // Load preview from /compare
      try {
        const r = await fetch(`${API_BASE}/compare`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: `session_id=${encodeURIComponent(sid)}`,
        });
        if (r.ok) {
          const d = await r.json();
          if (d.columns && d.anonymized_sample) {
            setPreviewCols(d.columns);
            setPreviewRows(d.anonymized_sample);
          }
          if (d.anonymized_shape?.[0]) {
            setTotalAnonRows(d.anonymized_shape[0]);
          }
        }
      } catch {}

      // Aux status
      try {
        const r = await fetch(`${API_BASE}/auxiliary-status/${sid}`);
        if (r.ok) {
          const aux = await r.json();
          setAuxStatus(aux);
          if (aux?.anonymized_rows && Number(aux.anonymized_rows) > 0) {
            setTotalAnonRows(prev => (prev > 0 ? prev : Number(aux.anonymized_rows)));
          }
        }
      } catch {}

      // Always attempt to restore persisted results on mount.
      // loadResults fetches each endpoint independently and only calls
      // setResult when data is actually returned, so it is safe to call
      // unconditionally — it is a no-op when the pipeline hasn't run yet.
      loadResults();
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  const toggleQI = (col: string) => {
    setSelectedQIs(prev => { const s = new Set(prev); s.has(col) ? s.delete(col) : s.add(col); return s; });
  };

  const uploadAux = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !sid) return;
    const fd = new FormData();
    fd.append('session_id', sid);
    fd.append('file', file);          // backend expects field name 'file'
    try {
      const r = await fetch(`${API_BASE}/upload-auxiliary`, { method: 'POST', body: fd });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        alert('Auxiliary upload failed: ' + ((err as { detail?: string }).detail ?? r.status));
        return;
      }
      const d = await r.json();
      setAuxStatus({ has_custom_auxiliary: true, auxiliary_filename: d.filename, auxiliary_rows: d.rows });
    } catch (e) { alert('Upload error: ' + (e instanceof Error ? e.message : String(e))); }
  };

  const runPipeline = async () => {
    if (!sid) return;
    if (!auxStatus?.has_custom_auxiliary) {
      alert('Please upload an auxiliary dataset before running the pipeline.');
      return;
    }
    setRunning(true);
    setProgress(0);
    setProgressMsg('Preparing…');

    // Reset step statuses
    const init: Record<string, StepStatus> = {};
    PIPELINE_STEPS.forEach(s => { init[s.id] = 'pending'; });
    setStepStatuses(init);

    const qiJson = JSON.stringify(Array.from(selectedQIs));
    const enabledModels = Object.entries(models).filter(([, v]) => v).map(([k]) => k);
    const modelsJson = JSON.stringify(enabledModels);

    // Helper: call one step, update its status, throw on failure
    const stepCall = async (
      stepId: string,
      label: string,
      endpoint: string,
      body: FormData,
      options?: { allow503?: boolean }
    ) => {
      setStepStatuses(prev => ({ ...prev, [stepId]: 'running' }));
      setProgressMsg(label);
      const res = await fetch(`${API_BASE}/${endpoint}`, { method: 'POST', body });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        if (options?.allow503 && res.status === 503) {
          setStepStatuses(prev => ({ ...prev, [stepId]: 'skip' }));
          setProgressMsg(`${label} unavailable (503), continuing…`);
          return null;
        }
        setStepStatuses(prev => ({ ...prev, [stepId]: 'error' }));
        throw new Error(`${label}: ${(d as { detail?: string }).detail || res.status}`);
      }
      setStepStatuses(prev => ({ ...prev, [stepId]: 'done' }));
      return res.json();
    };

    try {
      // Step 1: Data Inspection (Agent 1)
      const fd1 = new FormData(); fd1.append('session_id', sid);
      const inspectData = await stepCall('st1', 'Data Inspection…', 'inspect', fd1, { allow503: true });
      if (inspectData) {
        setInspectionResult(inspectData);
      }
      setProgress(14);

      // Step 2: Validate Identifiers (Agent 2)
      const fd2 = new FormData(); fd2.append('session_id', sid); fd2.append('quasi_identifiers', qiJson);
      await stepCall('st2', 'Validating Identifiers…', 'validate-identifiers', fd2, { allow503: true });
      setProgress(28);

      // Step 3: Generate Pairs (Agent 3)
      const fd3 = new FormData();
      fd3.append('session_id', sid);
      fd3.append('quasi_identifiers', qiJson);
      fd3.append('direct_identifiers', '[]');
      fd3.append('sensitive_attributes', '[]');
      fd3.append('mode', attackMode);  // use selected attack mode
      fd3.append('attacker_strength', strength);
      await stepCall('st3', 'Generating Pairs…', 'generate-pairs', fd3);
      setProgress(42);

      // Step 4: ML Attack (Agent 4)
      const fd4 = new FormData(); fd4.append('session_id', sid); fd4.append('model_names', modelsJson);
      await stepCall('st4', 'Training ML Attack…', 'run-attack', fd4);
      setProgress(57);

      // Step 5: Score Risk (Agent 5)
      const fd5 = new FormData(); fd5.append('session_id', sid);
      await stepCall('st5', 'Scoring Risk…', 'score-risk', fd5);
      setProgress(71);

      // Step 6: SHAP Explain (Agent 5c) — continue on error (mirrors Streamlit ok6s behaviour)
      const fd6 = new FormData(); fd6.append('session_id', sid);
      try {
        await stepCall('st6', 'Generating SHAP Explanations…', 'shap-explain', fd6);
      } catch (e: unknown) {
        console.warn('SHAP step failed, continuing to LLM:', e);
      }
      setProgress(85);

      // Step 7: LLM Explain (Agent 7) — key auto-read from server .env
      const fd7 = new FormData();
      fd7.append('session_id', sid);
      fd7.append('model_name', 'gpt-4o-mini');
      fd7.append('num_examples', '5');
      await stepCall('st7', 'Generating LLM Explanations…', 'explain-risk', fd7);

      setProgress(100);
      setProgressMsg('✓ Pipeline complete!');
      await loadResults();
    } catch (e: unknown) {
      setProgressMsg('Error: ' + (e instanceof Error ? e.message : String(e)));
      setStepStatuses(prev => {
        const updated = { ...prev };
        PIPELINE_STEPS.forEach(s => { if (updated[s.id] === 'pending') updated[s.id] = 'skip'; });
        return updated;
      });
    } finally {
      setRunning(false);
    }
  };

  const loadResults = async () => {
    if (!sid) return;
    const pipelineResult: PipelineResult = {};

    // ── Risk scores (required) ──────────────────────────────────────────────
    try {
      const riskRes = await fetch(`${API_BASE}/results/risk-scores/${sid}`);
      if (riskRes.ok) {
        const d = await riskRes.json();
        const records: RiskRecord[] = d.records ?? [];
        const cols: string[] = d.columns ?? [];
        const detectedRiskCol = detectRiskCol(cols);
        pipelineResult.risk_records = records;
        pipelineResult.risk_col = detectedRiskCol;
        pipelineResult.total_records = d.total;
        pipelineResult.columns = cols.filter(c =>
          !['anon_id', 'record_id', 'pair_index', 'label', detectedRiskCol].includes(c)
        );
        if (records.length > 0) {
          const scores = records.map(r => (r[detectedRiskCol] as number) ?? 0);
          const sorted = scores.slice().sort((a, b) => a - b);
          const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
          const p95 = sorted[Math.floor(scores.length * 0.95)] ?? 0;
          const p80 = sorted[Math.floor(scores.length * 0.80)] ?? 0;
          const p50 = sorted[Math.floor(scores.length * 0.50)] ?? 0;
          pipelineResult.overall_risk_score = avg;
          pipelineResult.p95 = p95;
          pipelineResult.p80 = p80;
          pipelineResult.p50 = p50;
          pipelineResult.critical_count = scores.filter(s => s >= p95).length;
          pipelineResult.high_risk_count  = scores.filter(s => s >= p80 && s < p95).length;
          pipelineResult.medium_count     = scores.filter(s => s >= p50 && s < p80).length;
          pipelineResult.low_count        = scores.filter(s => s < p50).length;
          pipelineResult.matched_count    = records.length;
        }
      }
    } catch { /* risk endpoint unreachable — skip */ }

    // ── SHAP global (optional) ──────────────────────────────────────────────
    try {
      const shapRes = await fetch(`${API_BASE}/results/shap-global/${sid}`);
      if (shapRes.ok) {
        const d = await shapRes.json();
        pipelineResult.shap_features = (d.records ?? []).map((r: Record<string, unknown>) => ({
          ...r,
          importance: (r.mean_abs_shap as number) ?? (r.importance as number) ?? 0,
        }));
      }
    } catch { /* SHAP step may have been skipped */ }

    // ── SHAP local top-features map (optional) ──────────────────────────────
    try {
      const shapLocalRes = await fetch(`${API_BASE}/results/shap-local/${sid}`);
      if (shapLocalRes.ok) {
        const d = await shapLocalRes.json();
        const records: { anon_id: string | number; feature: string; shap_value: number }[] = d.records ?? [];
        const grouped: Record<string, { feature: string; shap_value: number }[]> = {};
        for (const rec of records) {
          const key = String(rec.anon_id);
          if (!grouped[key]) grouped[key] = [];
          grouped[key].push({ feature: rec.feature, shap_value: rec.shap_value });
        }
        const normFeatureName = (raw: string): string => {
          if (GLOBAL_KEYWORDS.some(k => raw.toLowerCase().includes(k))) return 'Overall Similarity';
          const suffix = ENGINEERED_SUFFIXES.find(s => raw.endsWith(s));
          return suffix ? raw.slice(0, -suffix.length) : raw;
        };
        const topMap: Record<string, string> = {};
        for (const [id, feats] of Object.entries(grouped)) {
          const seen = new Set<string>();
          const top: string[] = [];
          for (const f of feats.sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value))) {
            const label = normFeatureName(f.feature);
            if (!seen.has(label)) { seen.add(label); top.push(label); }
            if (top.length === 3) break;
          }
          topMap[id] = top.join(', ');
        }
        setShapTopFeatures(topMap);
      }
    } catch { /* SHAP local step may have been skipped */ }

    // ── Matched row pairs (optional) ─────────────────────────────────────────
    try {
      const pairsRes = await fetch(`${API_BASE}/results/matched-row-pairs/${sid}?include_all=true&limit=0`);
      if (pairsRes.ok) {
        const d = await pairsRes.json();
        const pairs: MatchedRowPair[] = d.pairs ?? [];
        setMatchedPairs(pairs);
        setSelectedPairIdx(0);
        setShowFullPairData(false);
        setMatchedPairsMessage(d.message ?? '');
      }
    } catch {
      setMatchedPairs([]);
      setMatchedPairsMessage('Failed to load matched pairs from backend.');
    }

    // ── Vulnerable Columns (optional) ────────────────────────────────────────
    try {
      const vulnRes = await fetch(`${API_BASE}/results/vulnerable-columns/${sid}?min_score=0.01`);
      if (vulnRes.ok) {
        const d = await vulnRes.json();
        // Backend returns { columns: [...], records: [{column, vulnerable_score, ...}], ... }
        const vulnRecords = d.records ?? [];
        if (vulnRecords.length > 0) {
          pipelineResult.vulnerable_columns = vulnRecords.map((c: any) => ({
            columnName: c.column,
            score: c.vulnerable_score ?? 0,
          }));
        }
      }
    } catch { /* Vulnerable columns might not exist if analysis isn't complete */ }

    if (Object.keys(pipelineResult).length > 0) {
      setResult(pipelineResult);
    }
  };

  const downloadAnon = async (format: 'csv' | 'excel') => {
    const r = await fetch(`${API_BASE}/download-anonymized?session_id=${sid}&format=${format}`);
    if (!r.ok) { alert('Download failed'); return; }
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `anonymized_data.${format === 'excel' ? 'xlsx' : 'csv'}`;
    a.click();
  };

  const applyVulnerableColumns = async (columnsToApply?: string[]) => {
    if (!sid) return;
    try {
      setApplyingVulnCols(true);
      const targetColumns = columnsToApply || result?.vulnerable_columns?.map(c => c.columnName) || [];
      if (targetColumns.length === 0) {
        alert('No vulnerable columns found to apply.');
        setApplyingVulnCols(false);
        return;
      }
      
      const fd = new FormData();
      fd.append('session_id', sid);
      fd.append('top_k', String(targetColumns.length));
      fd.append('min_score', '0.01');
      fd.append('mode', 'merge');

      const r = await fetch(`${API_BASE}/apply-vulnerable-columns`, {
        method: 'POST',
        body: fd,
      });
      
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        alert('Failed to apply vulnerable columns: ' + (err.detail || r.status));
        return;
      }
      
      alert(`Successfully added ${targetColumns.length} vulnerable columns to Quasi-Identifiers. Let's re-run anonymization!`);
      // Update UI quasi-identifiers
      setSelectedQIs(prev => { 
        const s = new Set(prev); 
        targetColumns.forEach(c => s.add(c)); 
        return s; 
      });
      
      // Optionally, push user to anonymization page
      router.push(`/anonymization?session_id=${sid}`);
    } catch (e) {
      alert('Error applying vulnerable columns: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setApplyingVulnCols(false);
    }
  };

  const riskCol = result?.risk_col ?? 'max_attack_score';
  const filteredRecords = result?.risk_records?.filter(r => ((r[riskCol] as number) ?? 0) >= riskThreshold) ?? [];

  if (!sid) return <main className="page-container"><div className="alert-error">No session. <a href="/" className="underline text-blue-600">Go home</a></div></main>;

  return (
    <main className="page-container">
      <Breadcrumb />
      <div className="component-header">
        <h1>🔍 Re-identification Risk Assessment</h1>
        <p>Agentic ML pipeline to measure re-identification risk in your anonymized dataset</p>
      </div>

      <StatusBadge
        status={backendOk === null ? 'checking' : backendOk ? 'connected' : 'disconnected'}
        message={backendOk === null ? 'Checking backend…' : backendOk ? '✓ Backend connected' : '✗ Backend not connected'}
      />

      {noAnonWarning && (
        <div className="alert-warning">
          ⚠️ No anonymized data found in this session. Please run the <strong>Anonymization</strong> step first — the pipeline will fail without it.
        </div>
      )}

      {/* Dataset Info */}
      <div className="section">
        <h2>📊 Dataset Information</h2>
        <p><strong>Session:</strong> {sid} &nbsp;|&nbsp; <strong>Columns:</strong> {allCols.length}</p>
      </div>

      {/* Anonymized Preview */}
      {previewCols.length > 0 && (
        <div className="section">
          <h2>📋 Anonymized Dataset Preview</h2>
          <DataTable columns={previewCols} rows={previewRows} maxRows={10} />
        </div>
      )}

      {/* Auxiliary Upload */}
      <div className="section">
        <h2>📂 Auxiliary Dataset <span className="text-red-500 text-sm">* Required</span></h2>
        {auxStatus?.has_custom_auxiliary ? (
          <div className="alert-success">
            ✅ <strong>{auxStatus.auxiliary_filename}</strong> — {auxStatus.auxiliary_rows} rows uploaded
          </div>
        ) : (
          <div className="alert-warning">⚠️ No auxiliary dataset uploaded. Required before running the pipeline.</div>
        )}
        <p className="text-sm text-gray-500 mt-2">
          The auxiliary dataset represents the attacker's knowledge — external data used to try re-identification.
        </p>
        <input ref={auxInputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={uploadAux} />
        <button className="btn-primary mt-3" onClick={() => auxInputRef.current?.click()}>
          📁 Upload Auxiliary CSV / Excel
        </button>
      </div>

      {/* QI Chips */}
      {allCols.length > 0 && (
        <div className="section">
          <h2>🏷️ Quasi-Identifier Selection</h2>
          <p className="text-sm text-gray-500">Pre-populated from Quasi Selection step. Toggle to adjust.</p>
          <div className="flex flex-wrap gap-2 mt-3">
            {allCols.map(col => (
              <button
                key={col}
                onClick={() => toggleQI(col)}
                className={`px-3 py-1 rounded-full border text-sm transition-colors ${
                  selectedQIs.has(col)
                    ? 'bg-[#2196f3] text-white border-[#2196f3]'
                    : 'bg-white text-gray-600 border-gray-300 hover:border-[#2196f3]'
                }`}
              >
                {col}
              </button>
            ))}
          </div>
          <p className="text-sm text-gray-400 mt-2">{selectedQIs.size} columns selected</p>
        </div>
      )}

      {/* Run Pipeline */}
      <div className="section">
        <button className="btn-primary" onClick={runPipeline} disabled={running}>
          {running ? '⏳ Running Pipeline…' : '🚀 Run Full Risk Assessment'}
        </button>
        {running && (
          <div className="mt-4">
            <div className="w-full h-2 bg-gray-200 rounded overflow-hidden">
              <div className="h-full bg-gradient-to-r from-blue-400 to-green-400 rounded transition-all" style={{ width: `${progress}%` }} />
            </div>
            <p className="text-xs text-gray-500 mt-1">{progressMsg}</p>
          </div>
        )}
      </div>

      {/* Pipeline Steps */}
      {Object.keys(stepStatuses).length > 0 && (
        <div className="mt-8 mb-10 p-6 rounded-2xl bg-slate-900/40 border border-slate-800/60 shadow-xl backdrop-blur-sm">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2 m-0">
              <span className="text-blue-400">⚡</span> Agent Pipeline Execution
            </h2>
            {running && (
              <span className="flex items-center gap-2 text-xs font-semibold text-blue-400 bg-blue-500/10 px-3 py-1.5 rounded-full border border-blue-500/20">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                </span>
                Processing...
              </span>
            )}
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
            {PIPELINE_STEPS.map((s, idx) => {
              const st = stepStatuses[s.id] ?? 'pending';
              
              const styles: Record<StepStatus, { wrapper: string, iconBg: string, text: string, icon: JSX.Element }> = {
                done: {
                  wrapper: 'bg-gradient-to-br from-emerald-900/30 to-slate-900/50 border-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.1)]',
                  iconBg: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
                  text: 'text-emerald-300',
                  icon: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
                },
                running: {
                  wrapper: 'bg-gradient-to-br from-blue-900/40 to-slate-900/50 border-blue-400/50 shadow-[0_0_20px_rgba(59,130,246,0.2)] ring-1 ring-blue-400/30',
                  iconBg: 'bg-blue-500/20 text-blue-400 border border-blue-400/50 animate-pulse',
                  text: 'text-blue-300',
                  icon: <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                },
                error: {
                  wrapper: 'bg-gradient-to-br from-red-900/30 to-slate-900/50 border-red-500/30 shadow-[0_0_15px_rgba(239,68,68,0.1)]',
                  iconBg: 'bg-red-500/20 text-red-400 border border-red-500/30',
                  text: 'text-red-300',
                  icon: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                },
                skip: {
                  wrapper: 'bg-slate-800/30 border-slate-700/50',
                  iconBg: 'bg-slate-700/50 text-slate-400 border border-slate-600',
                  text: 'text-slate-400',
                  icon: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" /></svg>
                },
                pending: {
                  wrapper: 'bg-slate-900/30 border-slate-800/80 opacity-60',
                  iconBg: 'bg-slate-800 text-slate-500 border border-slate-700',
                  text: 'text-slate-500',
                  icon: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                },
              };

              const style = styles[st];

              return (
                <div key={s.id} className={`relative flex flex-col p-4 rounded-xl border backdrop-blur-sm transition-all duration-300 ${style.wrapper}`}>
                  <div className="flex items-start justify-between mb-3 z-10">
                    <div className={`flex items-center justify-center w-8 h-8 rounded-full ${style.iconBg}`}>
                      {style.icon}
                    </div>
                    <div className="text-[10px] font-black tracking-widest uppercase text-slate-500 bg-slate-900/50 px-2 py-1 rounded-md border border-slate-800/60 shadow-inner">
                      {s.agent}
                    </div>
                  </div>
                  
                  <div className={`text-sm font-bold leading-tight ${style.text} z-10`}>
                    {s.label}
                  </div>
                  
                  {st === 'running' && (
                    <div className="absolute bottom-0 left-0 h-1 bg-blue-500/50 animate-pulse rounded-b-xl" style={{ width: '100%' }}></div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Agent 1: Data Inspector Dashboard */}
      {inspectionResult && (

        <div className="section">
          <h2>🔍 Data Inspection Dashboard <span className="text-xs font-normal text-slate-400">(Agent 1)</span></h2>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mt-3">
            {[
              { label: 'Total Records', value: inspectionResult.data_profile?.dataset_overview?.total_rows?.toLocaleString() ?? '—' },
              { label: 'Total Columns', value: inspectionResult.data_profile?.dataset_overview?.total_columns?.toLocaleString() ?? '—' },
              { label: 'Duplicate Rows', value: inspectionResult.data_profile?.dataset_overview?.duplicate_rows?.toLocaleString() ?? '—' },
              { label: 'Records After Duplicates Removed', value: (() => {
                const total = inspectionResult.data_profile?.dataset_overview?.total_rows ?? null;
                const dup = inspectionResult.data_profile?.dataset_overview?.duplicate_rows ?? null;
                if (total != null && dup != null) return (total - dup).toLocaleString();
                return '—';
              })() },
              { label: 'Anomalies', value: inspectionResult.anomaly_report?.total_anomalies?.toString() ?? '0' },
            ].map(kpi => (
              <div key={kpi.label} className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3 text-center shadow-sm">
                <div className="text-lg font-bold text-slate-800 dark:text-slate-100">{kpi.value}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{kpi.label}</div>
              </div>
            ))}
          </div>

          {/* Schema Validation */}
          {inspectionResult.schema_validation && (
            <div className="mt-4">
              <h3 className="font-semibold text-sm mb-2">
                {inspectionResult.schema_validation.validation_passed
                  ? '✅ Schema Validation Passed'
                  : `⚠️ Schema Validation — ${inspectionResult.schema_validation.issues_found} issue(s)`}
              </h3>
              {inspectionResult.schema_validation.issues_found > 0 && (
                <div className="space-y-1 text-sm">
                  {inspectionResult.schema_validation.empty_columns.length > 0 && (
                    <div className="text-amber-700 dark:text-amber-400">Empty columns: {inspectionResult.schema_validation.empty_columns.join(', ')}</div>
                  )}
                  {inspectionResult.schema_validation.constant_columns.length > 0 && (
                    <div className="text-amber-700 dark:text-amber-400">Constant columns: {inspectionResult.schema_validation.constant_columns.join(', ')}</div>
                  )}
                  {inspectionResult.schema_validation.duplicate_columns.length > 0 && (
                    <div className="text-red-600 dark:text-red-400">Duplicate columns: {inspectionResult.schema_validation.duplicate_columns.join(', ')}</div>
                  )}
                  {inspectionResult.schema_validation.high_null_columns.map(c => (
                    <div key={c.column} className="text-amber-700 dark:text-amber-400">High null: <strong>{c.column}</strong> ({(c.null_rate * 100).toFixed(1)}% null)</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Missing Values Summary */}
          {((inspectionResult.missing_value_report?.missing_summary?.columns_with_missing ?? 0) > 0) && (
            <div className="mt-4">
              <h3 className="font-semibold text-sm mb-2">
                🕳️ Missing Values — {(inspectionResult.missing_value_report?.missing_summary?.total_missing ?? 0).toLocaleString()} total ({(((inspectionResult.missing_value_report?.missing_summary?.overall_missing_rate ?? 0) * 100)).toFixed(2)}%)
              </h3>
              <div className="space-y-1.5">
                {Object.entries(inspectionResult.missing_value_report?.column_analysis ?? {})
                  .sort(([, a], [, b]) => b.missing_rate - a.missing_rate)
                  .slice(0, 10)
                  .map(([col, info]) => (
                    <div key={col} className="flex items-center gap-3 text-sm">
                      <div className="w-36 font-medium text-slate-700 dark:text-slate-300 truncate">{col}</div>
                      <div className="flex-1 h-3 bg-slate-100 dark:bg-slate-700 rounded overflow-hidden">
                        <div className="h-full bg-amber-400 rounded" style={{ width: `${Math.min(info.missing_rate * 100, 100)}%` }} />
                      </div>
                      <div className="text-xs text-slate-500 w-20 text-right">{(info.missing_rate * 100).toFixed(1)}% ({info.missing_count})</div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Column Type Breakdown */}
          {inspectionResult.data_profile?.statistical_summary && (
            <div className="mt-4">
              <h3 className="font-semibold text-sm mb-2">📊 Column Types</h3>
              <div className="flex gap-3 flex-wrap text-sm">
                <span className="bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-3 py-1 rounded-full">Numeric: {inspectionResult.data_profile.statistical_summary.numeric_columns_count}</span>
                <span className="bg-green-50 dark:bg-green-900/40 text-green-700 dark:text-green-300 px-3 py-1 rounded-full">Categorical: {inspectionResult.data_profile.statistical_summary.categorical_columns_count}</span>
                <span className="bg-purple-50 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 px-3 py-1 rounded-full">Datetime: {inspectionResult.data_profile.statistical_summary.datetime_columns_count}</span>
              </div>
            </div>
          )}

          {/* Anomalies */}
          {((inspectionResult.anomaly_report?.anomalies?.length ?? 0) > 0) && (
            <div className="mt-4">
              <h3 className="font-semibold text-sm mb-2">🚨 Anomalies Detected ({inspectionResult.anomaly_report?.total_anomalies ?? 0})</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border border-slate-200 dark:border-slate-700 rounded">
                  <thead className="bg-slate-50 dark:bg-slate-800">
                    <tr>
                      <th className="text-left p-2 font-medium">Column</th>
                      <th className="text-left p-2 font-medium">Type</th>
                      <th className="text-right p-2 font-medium">Count / Ratio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(inspectionResult.anomaly_report?.anomalies ?? []).map((a, i) => (
                      <tr key={i} className="border-t border-slate-100 dark:border-slate-700">
                        <td className="p-2 font-medium">{a.column}</td>
                        <td className="p-2 text-slate-500">{a.type === 'statistical_outlier' ? 'Outlier (IQR 3×)' : 'High Cardinality'}</td>
                        <td className="p-2 text-right">
                          {a.count != null ? `${a.count} (${a.percentage?.toFixed(1)}%)` : `${a.unique_count} unique (${((a.unique_ratio ?? 0) * 100).toFixed(1)}%)`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Results Tabs */}
      {result && (
        <div className="section">
          <h2>📈 Risk Assessment Results</h2>

          {/* Tab Bar */}
          <div className="tab-bar">
            {(['summary','records','vulnerability','shap','llm'] as ActiveTab[]).map(tab => (
              <button key={tab} className={`tab-btn ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>
                {{ summary: '📊 Summary', records: '📋 Records', vulnerability: '🔍 Vulnerability', shap: '🧠 SHAP', llm: '💬 LLM' }[tab]}
              </button>
            ))}
          </div>

          {/* Summary Tab */}
          {activeTab === 'summary' && (() => {
            const matched = result.matched_count ?? 0;
            const totalFromAuxStatus = auxStatus?.anonymized_rows ?? 0;
            const total = totalAnonRows > 0
              ? totalAnonRows
              : totalFromAuxStatus > 0
                ? totalFromAuxStatus
                : (result.total_records ?? matched);
            const unmatched = Math.max(0, total - matched);
            const avgPct = (result.overall_risk_score ?? 0) * 100;
            const gaugeColor = avgPct >= 70 ? '#ef4444' : avgPct >= 30 ? '#eab308' : '#22c55e';
            const p95 = result.p95 ?? 0; const p80 = result.p80 ?? 0; const p50 = result.p50 ?? 0;
            const riskRows = [
              { label: `Critical (≥${(p95*100).toFixed(1)}%)`,  count: result.critical_count ?? 0, color: 'bg-red-500' },
              { label: `High (≥${(p80*100).toFixed(1)}%)`,      count: result.high_risk_count ?? 0, color: 'bg-orange-500' },
              { label: `Medium (≥${(p50*100).toFixed(1)}%)`,    count: result.medium_count ?? 0,    color: 'bg-yellow-500' },
              { label: `Low (<${(p50*100).toFixed(1)}%)`,       count: result.low_count ?? 0,       color: 'bg-green-500' },
            ];
            return (
              <div className="mt-4 space-y-8">
                {/* Gauge */}
                <div className="bg-slate-900/50 border border-slate-700/50 rounded-2xl p-6 flex flex-col md:flex-row items-center gap-8 shadow-inner">
                  <div className="flex-1">
                    <h3 className="text-xl font-bold text-slate-100 flex items-center gap-2 mb-2">
                      <span className="text-yellow-400">⚡</span> Average Attacker Confidence
                    </h3>
                    <p className="text-sm text-slate-400 leading-relaxed mb-4">
                      Average ML model confidence computed <strong>only on successfully matched records</strong>. This represents the model's reliance on learned patterns, not absolute re-identification probability.
                    </p>
                    <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3 text-xs text-blue-300">
                      <span className="font-semibold text-blue-200">ℹ️ Clarification:</span> This represents the ML attacker's confidence in its matching predictions. It measures how strongly the model relies on learned patterns.
                    </div>
                  </div>
                  
                  <div className="relative w-40 h-40 flex-shrink-0 drop-shadow-lg">
                    <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                      <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1e293b" strokeWidth="2.5" />
                      <circle cx="18" cy="18" r="15.9" fill="none" stroke={gaugeColor} strokeWidth="2.5"
                        strokeDasharray={`${avgPct} ${100 - avgPct}`} strokeLinecap="round" 
                        style={{ filter: `drop-shadow(0 0 6px ${gaugeColor}80)` }} />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className="text-3xl font-black tracking-tight" style={{ color: gaugeColor }}>{avgPct.toFixed(1)}%</span>
                      <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mt-1">Confidence</span>
                    </div>
                  </div>
                </div>

                {/* Match Coverage */}
                <div>
                  <h3 className="font-semibold text-slate-300 mb-3 text-lg flex items-center gap-2">📊 Dataset Context</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="bg-slate-900/30 border border-slate-700/50 rounded-xl p-5 text-center">
                      <div className="text-3xl font-black text-slate-300">{total.toLocaleString()}</div>
                      <div className="text-sm text-slate-400 mt-2 font-semibold">Total Anonymized Records</div>
                    </div>
                    <div className="bg-blue-900/20 border border-blue-800/50 rounded-xl p-5 text-center">
                      <div className="text-3xl font-black text-blue-400">{matched.toLocaleString()}</div>
                      <div className="text-sm text-blue-200 mt-2 font-semibold">Matched Records</div>
                      <div className="text-xs text-blue-400/60 mt-1">{matched && total ? `${((matched/total)*100).toFixed(1)}% coverage` : 'Scored by ML'}</div>
                    </div>
                    <div className="bg-slate-900/30 border border-slate-700/50 rounded-xl p-5 text-center opacity-70">
                      <div className="text-3xl font-black text-slate-500">{unmatched.toLocaleString()}</div>
                      <div className="text-sm text-slate-500 mt-2 font-semibold">Unmatched Records</div>
                      <div className="text-xs text-slate-600 mt-1">Risk unknown</div>
                    </div>
                  </div>
                </div>

                {/* Risk Breakdown */}
                <div>
                  <h3 className="font-semibold text-slate-300 mb-2 text-lg">📋 ML Risk Level Distribution</h3>
                  <div className="text-xs text-amber-500/80 mb-4 bg-amber-500/10 border border-amber-500/20 rounded-md p-2 inline-block">
                    ⚠️ <strong>IMPORTANT:</strong> This shows distribution for <strong>{matched.toLocaleString()} matched records only</strong>.
                  </div>
                  <div className="space-y-4 bg-slate-900/30 border border-slate-700/50 p-6 rounded-xl">
                    {riskRows.map(row => {
                      const pct = matched > 0 ? (row.count / matched) * 100 : 0;
                      return (
                        <div key={row.label} className="flex items-center gap-4">
                          <div className="w-48 text-sm font-semibold text-slate-300 flex-shrink-0">{row.label}</div>
                          <div className="flex-1 h-3 bg-slate-800 rounded-full overflow-hidden shadow-inner">
                            <div className={`h-full ${row.color} transition-all rounded-full`} style={{ width: `${pct}%`, boxShadow: `0 0 10px var(--tw-shadow-color)` }} />
                          </div>
                          <div className="text-sm font-bold w-28 text-right text-slate-200">
                            {row.count.toLocaleString()} <span className="text-slate-500 font-normal ml-1">({pct.toFixed(1)}%)</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Records Tab */}
          {activeTab === 'records' && (
            <div>
              <div className="alert-warning text-sm">⚠️ Only records matched to auxiliary data appear here.</div>
              <div className="flex items-center gap-3 mt-3 flex-wrap">
                <label className="text-sm font-medium">Min Risk: <span className="font-bold">{riskThreshold.toFixed(2)}</span></label>
                <input
                  type="range" min={0} max={1} step={0.05} value={riskThreshold}
                  onChange={e => setRiskThreshold(parseFloat(e.target.value))}
                  className="w-40"
                />
                <span className="text-sm text-gray-500">{filteredRecords.length} records</span>
              </div>
              {filteredRecords.length > 0 ? (
                <>
                <DataTable
                  columns={['anon_id', riskCol, ...(Object.keys(shapTopFeatures).length > 0 ? ['Top Risk Factors'] : []), ...(result?.columns?.slice(0, 5) ?? [])]}
                  rows={filteredRecords.map(r => {
                    const id = String(r.anon_id ?? r.record_id ?? r.anon_index ?? '');
                    return {
                      anon_id: id,
                      [riskCol]: typeof r[riskCol] === 'number' ? (r[riskCol] as number).toFixed(4) : r[riskCol],
                      ...(Object.keys(shapTopFeatures).length > 0 ? { 'Top Risk Factors': shapTopFeatures[id] ?? '—' } : {}),
                      ...Object.fromEntries((result?.columns?.slice(0, 5) ?? []).map(c => [c, r[c]])),
                    };
                  })}
                  maxRows={20}
                />
                <button
                  className="btn-secondary mt-3 text-sm"
                  onClick={() => {
                    const hasSHAP = Object.keys(shapTopFeatures).length > 0;
                    const cols = ['anon_id', riskCol, ...(hasSHAP ? ['Top Risk Factors'] : [])];
                    const csv = [
                      cols.join(','),
                      ...filteredRecords.map(r => {
                        const id = String(r.anon_id ?? r.record_id ?? r.anon_index ?? '');
                        return cols.map(c => {
                          if (c === 'anon_id') return id;
                          if (c === 'Top Risk Factors') return shapTopFeatures[id] ?? '';
                          return r[c] ?? '';
                        }).join(',');
                      }),
                    ].join('\n');
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
                    a.download = 'high_risk_records.csv';
                    a.click();
                  }}
                >📥 Download High Risk Records (CSV)</button>
                </>
              ) : (
                <p className="text-sm text-gray-500 mt-2">No records above threshold.</p>
              )}

              {/* Matched row comparison */}
              <div className="mt-6">
                <h3 className="font-semibold text-gray-700 mb-2">🔗 Pair Comparison (Auxiliary vs Anonymized)</h3>
                {matchedPairs.length > 0 ? (
                  <>
                    {(() => {
                      const pair = matchedPairs[selectedPairIdx];
                      if (!pair) return null;

                      const auxCols = Object.keys(pair.auxiliary_row ?? {});
                      const anonCols = Object.keys(pair.anonymized_row ?? {});
                      const unionCols = Array.from(new Set([...auxCols, ...anonCols]));
                      const statusesByCol = unionCols.map((col) => ({
                        col,
                        status: compareStatus(pair.auxiliary_row?.[col], pair.anonymized_row?.[col]),
                      }));
                      const comparedStatuses = statusesByCol.filter((x) => x.status !== 'missing');
                      const changedCount = comparedStatuses.filter((x) => x.status === 'changed').length;
                      const matchedCount = comparedStatuses.filter((x) => x.status === 'match').length;
                      const closeCount = comparedStatuses.filter((x) => x.status === 'close').length;
                      const excludedCount = statusesByCol.length - comparedStatuses.length;
                      const matchScore = pair.overall_similarity ?? 0;
                      const riskLevel = riskLevelFromAttackScore(pair.attack_score);
                      const visibleCols = showFullPairData ? unionCols : unionCols.slice(0, 6);

                      return (
                        <div className="rounded-xl border border-slate-700 bg-slate-900/95 p-4 space-y-4 text-slate-100">
                          <div className="flex items-center gap-3 flex-wrap">
                            <label className="text-sm font-medium text-slate-300">Pair:</label>
                            <select
                              className="rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100"
                              value={selectedPairIdx}
                              onChange={(e) => {
                                setSelectedPairIdx(Number(e.target.value));
                                setShowFullPairData(false);
                              }}
                            >
                              {matchedPairs.map((p, i) => (
                                <option key={`${p.aux_index}-${p.anon_index}-${i}`} value={i}>
                                  Aux #{p.aux_index} → Anon #{p.anon_index}
                                  {p.overall_similarity != null ? ` (sim ${p.overall_similarity.toFixed(3)})` : ''}
                                </option>
                              ))}
                            </select>
                            <span className="text-xs text-slate-400">{matchedPairs.length} pair rows loaded</span>
                          </div>

                          <div className="flex items-center gap-2 flex-wrap text-xs">
                            <span className="rounded px-2 py-1 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">Match Score: {matchScore.toFixed(3)}</span>
                            <span className={`rounded px-2 py-1 border ${riskLevel === 'High' ? 'bg-red-500/20 text-red-300 border-red-500/40' : riskLevel === 'Medium' ? 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'}`}>
                              Risk Level: {riskLevel}
                            </span>
                            <span className="rounded px-2 py-1 bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">Matched: {matchedCount}</span>
                            <span className="rounded px-2 py-1 bg-lime-500/20 text-lime-300 border border-lime-500/40">Close: {closeCount}</span>
                            <span className="rounded px-2 py-1 bg-amber-500/20 text-amber-300 border border-amber-500/40">Changed: {changedCount}</span>
                            <span className="rounded px-2 py-1 bg-slate-500/20 text-slate-300 border border-slate-500/40">Excluded (both empty): {excludedCount}</span>
                            <span className="text-slate-400">Total compared fields: {comparedStatuses.length}</span>
                          </div>

                          <div className="overflow-x-auto rounded-lg border border-slate-700">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="bg-slate-800 text-slate-300">
                                  <th>Column</th>
                                  <th>Auxiliary Value</th>
                                  <th>Anonymized Value</th>
                                  <th>Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {visibleCols.map((col) => {
                                  const auxVal = pair.auxiliary_row?.[col];
                                  const anonVal = pair.anonymized_row?.[col];
                                  const status = compareStatus(auxVal, anonVal);
                                  return (
                                    <tr key={col} className="border-t border-slate-800 bg-slate-900/70">
                                      <td className="p-2 font-medium text-slate-200">{col}</td>
                                      <td className="p-2">
                                        <span className={`px-2 py-0.5 rounded text-xs ${status === 'match' ? 'bg-emerald-500/20 text-emerald-300' : status === 'close' ? 'bg-lime-500/20 text-lime-300' : status === 'missing' ? 'bg-slate-500/20 text-slate-300' : 'bg-rose-500/20 text-rose-300'}`}>
                                          {String(auxVal ?? '—')}
                                        </span>
                                      </td>
                                      <td className="p-2 text-slate-300">{String(anonVal ?? '—')}</td>
                                      <td className="p-2">
                                        {status === 'match' && <span className="px-2 py-0.5 rounded text-xs bg-emerald-500/20 text-emerald-300">Match</span>}
                                        {status === 'close' && <span className="px-2 py-0.5 rounded text-xs bg-lime-500/20 text-lime-300">Close</span>}
                                        {status === 'changed' && <span className="px-2 py-0.5 rounded text-xs bg-amber-500/20 text-amber-300">Changed</span>}
                                        {status === 'missing' && <span className="px-2 py-0.5 rounded text-xs bg-slate-500/20 text-slate-300">Both Empty</span>}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>

                          {unionCols.length > 6 && (
                            <div className="flex justify-center">
                              <button
                                onClick={() => setShowFullPairData(v => !v)}
                                className="px-4 py-1.5 rounded-md border border-slate-600 bg-slate-800 text-slate-200 text-sm hover:bg-slate-700 transition"
                              >
                                {showFullPairData ? 'Hide Extra Columns ▲' : 'Show Full Data ▼'}
                              </button>
                            </div>
                          )}

                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pt-1">
                            <div>
                              <h4 className="font-medium text-sm text-slate-300 mb-1">Auxiliary Row (index: {pair.aux_index})</h4>
                              <DataTable columns={auxCols} rows={[pair.auxiliary_row]} maxRows={1} />
                            </div>
                            <div>
                              <h4 className="font-medium text-sm text-slate-300 mb-1">Anonymized Row (index: {pair.anon_index})</h4>
                              <DataTable columns={anonCols} rows={[pair.anonymized_row]} maxRows={1} />
                            </div>
                          </div>
                        </div>
                      );
                    })()}
                  </>
                ) : (
                  <p className="text-sm text-gray-500">
                    {matchedPairsMessage || 'No matched row pairs found yet. Run the pipeline first.'}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Vulnerability Tab */}
          {activeTab === 'vulnerability' && (() => {
            const hasVulnData = result.vulnerable_columns && result.vulnerable_columns.length > 0;
            const hasShapData = result.shap_features && result.shap_features.length > 0;
            
            if (!hasVulnData && !hasShapData)
              return <p className="text-sm text-slate-500 mt-2">No Vulnerability or SHAP data available. Run the pipeline first.</p>;

            // Build a lookup from SHAP aggregation for feature count info
            const shapAggregated = hasShapData ? aggregateShapFeatures(result.shap_features!) : [];
            const shapLookup: Record<string, { rawFeatures: string[]; avgImportance: number; maxImportance: number }> = {};
            for (const item of shapAggregated) {
              shapLookup[item.col.toLowerCase()] = item;
            }

            return (
              <div className="mt-2">
                <div className="mb-6 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 shadow-sm flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-slate-800 dark:text-slate-200 mb-1 flex items-center gap-2">
                      <span className="text-xl">🎯</span> Column-Level Vulnerability Analysis
                    </h3>
                    <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                      Vulnerability scores combine SHAP feature importance (70%) and pair-risk correlation (30%) to identify 
                      which columns the ML attacker relies on most. Higher scores mean the column is more vulnerable to re-identification.
                    </p>
                  </div>
                  {hasVulnData && (
                    <button 
                      onClick={() => applyVulnerableColumns()}
                      disabled={applyingVulnCols}
                      className="shrink-0 flex items-center gap-2 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white font-bold py-2.5 px-5 rounded-lg shadow-md hover:shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {applyingVulnCols ? '⏳ Applying...' : '🛡️ Apply to Anonymization'}
                    </button>
                  )}
                </div>

                {hasVulnData ? (
                  <>
                    {/* Column cards with consistent vulnerability score */}
                    <h4 className="text-md font-bold text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
                      <span className="text-red-500">🚨</span> Column Vulnerability Ranking
                    </h4>

                    {/* Table header */}
                    <div className="grid gap-4 border-b border-slate-200 dark:border-slate-700 pb-3 mb-2 px-4" style={{ gridTemplateColumns: '2fr 1fr 1fr' }}>
                      <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Column</div>
                      <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-center">Vulnerability Score</div>
                      <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-center">Risk Level</div>
                    </div>

                    <div className="space-y-3">
                      {result.vulnerable_columns!.map((vc) => {
                        const score = vc.score;
                        const riskLevel = score >= 60 ? 'Critical' : score >= 40 ? 'High' : score >= 20 ? 'Medium' : 'Low';
                        const riskColor = score >= 60 ? 'text-red-400' : score >= 40 ? 'text-orange-400' : score >= 20 ? 'text-yellow-400' : 'text-emerald-400';
                        const riskBg = score >= 60 ? 'bg-red-500/15 border-red-500/30' : score >= 40 ? 'bg-orange-500/15 border-orange-500/30' : score >= 20 ? 'bg-yellow-500/15 border-yellow-500/30' : 'bg-emerald-500/15 border-emerald-500/30';
                        const shapInfo = shapLookup[vc.columnName.toLowerCase()];
                        const featureCount = shapInfo?.rawFeatures?.length ?? 0;

                        return (
                          <div key={vc.columnName} className="grid gap-4 items-center bg-white dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800 rounded-xl p-4 hover:shadow-md dark:hover:bg-slate-800/60 transition-all" style={{ gridTemplateColumns: '2fr 1fr 1fr' }}>
                            <div>
                              <div className="font-bold text-lg text-slate-800 dark:text-slate-100">{vc.columnName}</div>
                              {featureCount > 0 && (
                                <div className="text-xs text-slate-500 dark:text-slate-400 mt-1.5 flex items-center gap-1.5">
                                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500/60 inline-block"></span>
                                  Derived from {featureCount} underlying ML feature{featureCount !== 1 ? 's' : ''}
                                </div>
                              )}
                            </div>
                            <div className="flex justify-center">
                              <SemiGauge value={score} label="Vulnerability Score" />
                            </div>
                            <div className="flex justify-center">
                              <span className={`px-3 py-1.5 rounded-lg border text-sm font-bold ${riskBg} ${riskColor}`}>
                                {riskLevel}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </>
                ) : hasShapData && (
                  <>
                    {/* Fallback: show raw SHAP aggregation when vulnerable_columns endpoint has no data */}
                    <h4 className="text-md font-bold text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
                      <span className="text-blue-500">🧠</span> Column ML Reliance (SHAP Aggregation)
                    </h4>
                    <div className="grid gap-4 border-b border-slate-200 dark:border-slate-700 pb-3 mb-2 px-4" style={{ gridTemplateColumns: '2fr 1fr 1fr' }}>
                      <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Anonymized Column</div>
                      <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-center">Avg ML Reliance</div>
                      <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-center">Max ML Reliance</div>
                    </div>
                    <div className="space-y-3">
                      {shapAggregated.map(({ col, avgImportance, maxImportance, rawFeatures }) => {
                        const avgPct = Math.min(avgImportance * 100, 100);
                        const maxPct = Math.min(maxImportance * 100, 100);
                        return (
                          <div key={col} className="grid gap-4 items-center bg-white dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800 rounded-xl p-4 hover:shadow-md dark:hover:bg-slate-800/60 transition-all" style={{ gridTemplateColumns: '2fr 1fr 1fr' }}>
                            <div>
                              <div className="font-bold text-lg text-slate-800 dark:text-slate-100">{col}</div>
                              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1.5 flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-blue-500/60 inline-block"></span>
                                Derived from {rawFeatures.length} underlying ML feature{rawFeatures.length !== 1 ? 's' : ''}
                              </div>
                            </div>
                            <div className="flex justify-center">
                              <SemiGauge value={avgPct} label="Average Contribution" />
                            </div>
                            <div className="flex justify-center">
                              <SemiGauge value={maxPct} label="Maximum Contribution" />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            );
          })()}

          {/* SHAP Tab */}
          {activeTab === 'shap' && (
            <div>
              <div className="alert-info text-sm">ℹ️ SHAP values show how much the ML attacker relies on each feature. Showing aggregated view — expand for raw engineered features.</div>
              {result.shap_features?.length ? (
                <>
                  {/* Aggregated table */}
                  <DataTable
                    columns={['Column', 'Avg SHAP', 'Max SHAP', 'Raw Features']}
                    rows={aggregateShapFeatures(result.shap_features).map(({ col, avgImportance, maxImportance, rawFeatures }) => ({
                      'Column': col,
                      'Avg SHAP': avgImportance.toFixed(4),
                      'Max SHAP': maxImportance.toFixed(4),
                      'Raw Features': rawFeatures.join(', '),
                    }))}
                    maxRows={50}
                  />
                  {/* Raw features expander */}
                  <details className="mt-3">
                    <summary className="cursor-pointer text-sm font-medium text-blue-600 hover:underline">🔧 View Raw Engineered Features</summary>
                    <DataTable
                      columns={['feature', 'importance']}
                      rows={result.shap_features.map(f => ({ feature: f.feature, importance: typeof f.importance === 'number' ? f.importance.toFixed(4) : f.importance }))}
                      maxRows={50}
                    />
                  </details>
                </>
              ) : <p className="text-sm text-gray-500 mt-2">No SHAP data available.</p>}
            </div>
          )}

          {/* LLM Tab */}
          {activeTab === 'llm' && (
            <LlmTabAutoLoader
              sid={sid}
              llmResult={llmResult}
              setLlmResult={setLlmResult}
              selectedLlmIdx={selectedLlmIdx}
              setSelectedLlmIdx={setSelectedLlmIdx}
            />
          )}
        </div>
      )}

      {/* Download */}
      <div className="section">
        <h2>💾 Download Anonymized Data</h2>
        <div className="flex gap-3 flex-wrap mt-2">
          <button className="btn-success" onClick={() => downloadAnon('csv')}>📥 Download CSV</button>
          <button className="btn-info" onClick={() => downloadAnon('excel')}>📥 Download Excel</button>
        </div>
      </div>

      {/* Navigation */}
      <div className="section">
        <h3>Other Components</h3>
        <div className="flex gap-3 flex-wrap mt-2">
          <button className="btn-secondary" onClick={() => router.push(`/anonymization?session_id=${sid}`)}>Anonymization</button>
          <button className="btn-secondary" onClick={() => router.push(`/synthetic-data?session_id=${sid}`)}>Synthetic Data</button>
          <button className="btn-secondary" onClick={() => router.push('/')}>Home</button>
        </div>
      </div>
    </main>
  );
}

export default function ReidentificationPage() {
  return <Suspense fallback={<div className="page-container"><p>Loading…</p></div>}><ReidentificationInner /></Suspense>;
}
