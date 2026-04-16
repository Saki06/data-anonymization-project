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

function isNumericValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return false;
  return !Number.isNaN(Number(value));
}

function compareStatus(auxValue: unknown, anonValue: unknown): 'match' | 'close' | 'changed' {
  if (valuesMatch(auxValue, anonValue)) return 'match';
  if (isNumericValue(auxValue) && isNumericValue(anonValue)) {
    const delta = Math.abs(Number(auxValue) - Number(anonValue));
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

interface PipelineResult {
  overall_risk_score?: number;
  total_records?: number;
  high_risk_count?: number;
  matched_count?: number;
  risk_records?: RiskRecord[];
  risk_col?: string;
  shap_features?: ShapFeature[];
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

  if (loading) return <p className="text-sm text-gray-400 mt-3">⏳ Loading LLM explanations…</p>;
  if (!llmResult) return <p className="text-sm text-gray-500 mt-3">ℹ️ No LLM explanations available yet. Run the pipeline first — explanations are generated automatically.</p>;

  return (
    <div className="mt-3">
      {/* Dataset Summary */}
      {llmResult.summary && (
        <>
          <h4 className="font-semibold text-gray-700 mb-2">📊 Dataset Risk Summary</h4>
          <div className="bg-slate-100 border-l-4 border-slate-700 rounded p-4 text-sm whitespace-pre-wrap font-mono leading-relaxed text-slate-800">{llmResult.summary}</div>
        </>
      )}

      {llmResult.explanations?.length ? (
        <>
          <h4 className="mt-5 font-semibold text-gray-700">📝 Individual Record Explanations</h4>

          {/* Record Selector */}
          <div className="mt-2">
            <label className="text-xs font-semibold text-gray-500">Select a record to view explanation:</label>
            <select
              className="mt-1 block w-full border border-gray-300 rounded p-2 text-sm"
              value={selectedLlmIdx}
              onChange={e => setSelectedLlmIdx(Number(e.target.value))}
            >
              {llmResult.explanations.map((exp, i) => {
                const rs = exp.risk_score ?? 0;
                const icon = rs >= 0.7 ? '🔴' : rs >= 0.3 ? '🟡' : '🟢';
                return (
                  <option key={exp.record_id} value={i}>
                    Record {exp.record_id} — Risk: {rs.toFixed(4)} {icon}
                  </option>
                );
              })}
            </select>
          </div>

          {/* Selected record detail */}
          {(() => {
            const exp = llmResult.explanations![selectedLlmIdx];
            if (!exp) return null;
            const rs = exp.risk_score ?? 0;
            const cat = rs >= 0.7 ? 'HIGH' : rs >= 0.3 ? 'MEDIUM' : 'LOW';
            const icon = cat === 'HIGH' ? '🔴' : cat === 'MEDIUM' ? '🟡' : '🟢';
            const [bg, border] = cat === 'HIGH' ? ['#ffebee','#f44336'] : cat === 'MEDIUM' ? ['#fff3e0','#ff9800'] : ['#e8f5e9','#4caf50'];
            return (
              <div className="mt-3">
                <div className="grid grid-cols-3 gap-3 mb-3">
                  {[
                    { label: 'Record ID', val: exp.record_id },
                    { label: 'Risk Score', val: rs.toFixed(4) },
                    { label: 'Risk Level', val: `${icon} ${cat}` },
                  ].map(m => (
                    <div key={m.label} className="bg-gray-50 border border-gray-200 rounded p-3 text-center">
                      <div className="text-lg font-bold text-gray-800">{m.val}</div>
                      <div className="text-xs text-gray-500 mt-0.5">{m.label}</div>
                    </div>
                  ))}
                </div>
                <h5 className="text-sm font-semibold text-gray-600 mb-1">🤖 AI-Generated Explanation</h5>
                <div className="p-4 rounded-lg text-sm text-gray-800 border-l-4"
                  style={{ backgroundColor: bg, borderColor: border }}>
                  {exp.explanation}
                </div>
              </div>
            );
          })()}

          {/* All records collapsible */}
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium text-blue-600 hover:underline">📚 View All Explained Records</summary>
            <div className="mt-2 space-y-2">
              {llmResult.explanations.map((exp, i) => {
                const rs = exp.risk_score ?? 0;
                const icon = rs >= 0.7 ? '🔴' : rs >= 0.3 ? '🟡' : '🟢';
                return (
                  <div key={exp.record_id} className="border border-slate-200 shadow-sm rounded p-3 text-sm bg-white">
                    <div className="font-semibold text-slate-800">{icon} Record {exp.record_id} <span className="text-slate-500 font-normal">(Risk: {rs.toFixed(4)})</span></div>
                    <p className="text-slate-600 mt-1 text-xs">{exp.explanation.slice(0, 200)}…
                      <button className="ml-1 text-blue-600 hover:underline font-medium" onClick={() => setSelectedLlmIdx(i)}>view full</button>
                    </p>
                  </div>
                );
              })}
            </div>
          </details>
        </>
      ) : (
        <p className="text-sm text-gray-500 mt-3">No explanations found in results.</p>
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

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 120 68" width="130" height="68">
        {/* Background track */}
        <path d={arcPath(0, 100)} fill="none" stroke="#e2e8f0" strokeWidth="14" strokeLinecap="butt" />
        {/* Color bands: green 0–40%, yellow 40–70%, red 70–100% */}
        <path d={arcPath(0, 40)}   fill="none" stroke="#22c55e" strokeWidth="10" strokeLinecap="butt" />
        <path d={arcPath(40, 70)}  fill="none" stroke="#eab308" strokeWidth="10" strokeLinecap="butt" />
        <path d={arcPath(70, 100)} fill="none" stroke="#ef4444" strokeWidth="10" strokeLinecap="butt" />
        {/* Dark fill arc 0 → value */}
        {v > 0.5 && (
          <path d={arcPath(0, v)} fill="none" stroke="#334155" strokeWidth="14" strokeLinecap="butt" />
        )}
        {/* Tick labels */}
        <text x={p0x - 7}  y={p0y + 5}   fontSize="9" fontWeight="600" fill="#e2e8f0" textAnchor="middle">0</text>
        <text x={p50x}     y={p50y - 4}  fontSize="9" fontWeight="600" fill="#e2e8f0" textAnchor="middle">50</text>
        <text x={p100x + 7} y={p100y + 5} fontSize="9" fontWeight="600" fill="#e2e8f0" textAnchor="middle">100</text>
        {/* Value */}
        <text x={cx} y={cy + 10} fontSize="11" fontWeight="bold" fill="#f1f5f9" textAnchor="middle">{v.toFixed(1)}</text>
      </svg>
      <div className="text-xs text-slate-500 text-center -mt-1 leading-tight" style={{ maxWidth: 130 }}>{label}</div>
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
      const pairsRes = await fetch(`${API_BASE}/results/matched-row-pairs/${sid}?limit=200`);
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
        <div className="section">
          <h2>🔄 Pipeline Steps</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 mt-3">
            {PIPELINE_STEPS.map(s => {
              const st = stepStatuses[s.id] ?? 'pending';
              const colorMap: Record<StepStatus, string> = {
                done:    'border-green-400 bg-green-50',
                running: 'border-blue-400 bg-blue-50',
                error:   'border-red-400 bg-red-50',
                skip:    'border-gray-300 bg-gray-50',
                pending: 'border-gray-200 bg-white',
              };
              const icon = st === 'done' ? '✅' : st === 'running' ? '⏳' : st === 'error' ? '❌' : st === 'skip' ? '⏭' : '⬜';
              return (
                <div key={s.id} className={`border rounded-lg p-3 ${colorMap[st]}`}>
                  <div className="text-xs text-gray-400 font-semibold uppercase tracking-wide">{s.agent}</div>
                  <div className="text-sm font-semibold text-gray-700 mt-1">{s.label}</div>
                  <div className="text-lg mt-1">{icon}</div>
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
            const gaugeColor = avgPct >= 70 ? '#dc3545' : avgPct >= 30 ? '#ffc107' : '#28a745';
            const p95 = result.p95 ?? 0; const p80 = result.p80 ?? 0; const p50 = result.p50 ?? 0;
            const riskRows = [
              { label: `Critical (≥${(p95*100).toFixed(1)}%)`,  count: result.critical_count ?? 0, color: 'bg-red-500' },
              { label: `High (≥${(p80*100).toFixed(1)}%)`,      count: result.high_risk_count ?? 0, color: 'bg-orange-400' },
              { label: `Medium (≥${(p50*100).toFixed(1)}%)`,    count: result.medium_count ?? 0,    color: 'bg-yellow-400' },
              { label: `Low (<${(p50*100).toFixed(1)}%)`,       count: result.low_count ?? 0,       color: 'bg-green-500' },
            ];
            return (
              <div className="mt-3 space-y-5">
                {/* Gauge */}
                <div>
                  <h3 className="font-semibold text-gray-700 mb-1">⚡ Average ML Attacker Confidence (Matched Records Only)</h3>
                  <p className="text-xs text-gray-500 mb-2">Average ML model confidence computed <strong>only on successfully matched records</strong>. Represents model's reliance on learned patterns, not absolute re-identification probability.</p>
                  <div className="flex items-center gap-4">
                    <div className="relative w-32 h-32 flex-shrink-0">
                      <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e9ecef" strokeWidth="3" />
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke={gaugeColor} strokeWidth="3"
                          strokeDasharray={`${avgPct} ${100 - avgPct}`} strokeLinecap="round" />
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center rotate-0">
                        <span className="text-xl font-bold" style={{ color: gaugeColor }}>{avgPct.toFixed(1)}%</span>
                        <span className="text-xs text-gray-400">confidence</span>
                      </div>
                    </div>
                    <div className="alert-info text-sm flex-1">
                      ℹ️ <strong>Clarification:</strong> This represents the ML attacker's <strong>confidence in its matching predictions</strong>, not absolute re-identification probability. It measures how strongly the model relies on learned patterns.
                    </div>
                  </div>
                </div>

                {/* Match Coverage */}
                <div>
                  <h3 className="font-semibold text-gray-700 mb-2">📊 Dataset Context</h3>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: 'Total Anonymized Records', val: total, sub: '' },
                      { label: 'Matched Records (scored)', val: matched, sub: matched && total ? `${((matched/total)*100).toFixed(1)}% coverage` : '' },
                      { label: 'Unmatched Records', val: unmatched, sub: 'risk unknown' },
                    ].map(m => (
                      <div key={m.label} className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-center">
                        <div className="text-2xl font-bold text-blue-900">{m.val}</div>
                        <div className="text-xs text-gray-600 mt-0.5 font-medium">{m.label}</div>
                        {m.sub && <div className="text-xs text-gray-400">{m.sub}</div>}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Risk Breakdown */}
                <div>
                  <h3 className="font-semibold text-gray-700 mb-1">📋 ML Risk Level Distribution among {matched.toLocaleString()} Matched Records</h3>
                  <div className="alert-warning text-xs mb-3">
                    ⚠️ <strong>IMPORTANT:</strong> This shows ML model confidence distribution for <strong>{matched.toLocaleString()} matched records only</strong>. Unmatched records are excluded.
                  </div>
                  <div className="space-y-2">
                    {riskRows.map(row => {
                      const pct = matched > 0 ? (row.count / matched) * 100 : 0;
                      return (
                        <div key={row.label} className="flex items-center gap-3">
                          <div className="w-48 text-sm text-white flex-shrink-0">{row.label}</div>
                          <div className="flex-1 h-5 bg-gray-100 rounded overflow-hidden">
                            <div className={`h-full ${row.color} rounded transition-all`} style={{ width: `${pct}%` }} />
                          </div>
                          <div className="text-sm font-semibold w-20 text-right">{row.count.toLocaleString()} <span className="text-gray-400 font-normal">({pct.toFixed(1)}%)</span></div>
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
                    const id = String(r.anon_id ?? r.record_id ?? '');
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
                        const id = String(r.anon_id ?? r.record_id ?? '');
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
                <h3 className="font-semibold text-gray-700 mb-2">🔗 Matched Pair Comparison (Auxiliary vs Anonymized)</h3>
                {matchedPairs.length > 0 ? (
                  <>
                    {(() => {
                      const pair = matchedPairs[selectedPairIdx];
                      if (!pair) return null;

                      const auxCols = Object.keys(pair.auxiliary_row ?? {});
                      const anonCols = Object.keys(pair.anonymized_row ?? {});
                      const unionCols = Array.from(new Set([...auxCols, ...anonCols]));
                      const changedCount = unionCols.filter((col) => compareStatus(pair.auxiliary_row?.[col], pair.anonymized_row?.[col]) === 'changed').length;
                      const matchScore = pair.overall_similarity ?? 0;
                      const riskLevel = riskLevelFromAttackScore(pair.attack_score);
                      const visibleCols = showFullPairData ? unionCols : unionCols.slice(0, 6);

                      return (
                        <div className="rounded-xl border border-slate-700 bg-slate-900/95 p-4 space-y-4 text-slate-100">
                          <div className="flex items-center gap-3 flex-wrap">
                            <label className="text-sm font-medium text-slate-300">Matched Pair:</label>
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
                            <span className="text-xs text-slate-400">{matchedPairs.length} matched pairs loaded</span>
                          </div>

                          <div className="flex items-center gap-2 flex-wrap text-xs">
                            <span className="rounded px-2 py-1 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">Match Score: {matchScore.toFixed(3)}</span>
                            <span className={`rounded px-2 py-1 border ${riskLevel === 'High' ? 'bg-red-500/20 text-red-300 border-red-500/40' : riskLevel === 'Medium' ? 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'}`}>
                              Risk Level: {riskLevel}
                            </span>
                            <span className="rounded px-2 py-1 bg-amber-500/20 text-amber-300 border border-amber-500/40">Changed: {changedCount}</span>
                            <span className="text-slate-400">Total compared fields: {unionCols.length}</span>
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
                                        <span className={`px-2 py-0.5 rounded text-xs ${status === 'match' ? 'bg-emerald-500/20 text-emerald-300' : status === 'close' ? 'bg-lime-500/20 text-lime-300' : 'bg-rose-500/20 text-rose-300'}`}>
                                          {String(auxVal ?? '—')}
                                        </span>
                                      </td>
                                      <td className="p-2 text-slate-300">{String(anonVal ?? '—')}</td>
                                      <td className="p-2">
                                        {status === 'match' && <span className="px-2 py-0.5 rounded text-xs bg-emerald-500/20 text-emerald-300">Match</span>}
                                        {status === 'close' && <span className="px-2 py-0.5 rounded text-xs bg-lime-500/20 text-lime-300">Close</span>}
                                        {status === 'changed' && <span className="px-2 py-0.5 rounded text-xs bg-amber-500/20 text-amber-300">Changed</span>}
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
            if (!result.shap_features?.length)
              return <p className="text-sm text-slate-500 mt-2">No SHAP data available.</p>;

            const aggregated = aggregateShapFeatures(result.shap_features);

            return (
              <div>
                <p className="text-sm text-slate-500 mb-4">Column-level vulnerability based on ML attacker SHAP importance. Engineered features are aggregated back to their original column names.</p>

                {/* Table header */}
                <div className="grid gap-4 border-b border-slate-200 dark:border-slate-700 pb-2 mb-1" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
                  <div className="text-sm font-semibold text-slate-700 dark:text-slate-300">Anonymized Column</div>
                  <div className="text-sm font-semibold text-slate-700 dark:text-slate-300 text-center">ML Reliance (Avg)</div>
                  <div className="text-sm font-semibold text-slate-700 dark:text-slate-300 text-center">ML Reliance (Max)</div>
                </div>

                {aggregated.map(({ col, avgImportance, maxImportance, rawFeatures }) => {
                  const avgPct = Math.min(avgImportance * 100, 100);
                  const maxPct = Math.min(maxImportance * 100, 100);
                  return (
                    <div key={col} className="grid gap-4 items-center border-b border-slate-100 dark:border-slate-700 py-3" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
                      <div>
                        <div className="font-semibold text-sm text-slate-900 dark:text-slate-100">{col}</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400 italic">(from {rawFeatures.length} ML feature{rawFeatures.length !== 1 ? 's' : ''})</div>
                      </div>
                      <div className="flex justify-center">
                        <SemiGauge value={avgPct} label="Avg ML Contribution" />
                      </div>
                      <div className="flex justify-center">
                        <SemiGauge value={maxPct} label="Max ML Contribution" />
                      </div>
                    </div>
                  );
                })}
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
