'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useSession, API_BASE } from '@/lib/SessionContext';
import Breadcrumb from '@/components/Breadcrumb';
import StatusBadge from '@/components/StatusBadge';
import DataTable from '@/components/DataTable';

// ─── types ────────────────────────────────────────────────────────────────────

interface ColumnMeta {
  column: string;
  dtype: string;
  role: string;
  action: string;
}

interface SelfCheck {
  no_direct_identifiers: boolean;
  row_count_match: boolean;
  no_nan_explosion: boolean;
  epsilon_valid: boolean;
}

interface GenerateResult {
  original_shape: [number, number];
  synthetic_shape: [number, number];
  columns: string[];
  dropped_columns: string[];
  sample_data: Record<string, unknown>[];
  epsilon: number;
  seed: number;
  strata_keys: string[];
  self_check: SelfCheck;
}

interface UtilityCol {
  Column: string;
  TVD?: number;
  'KS Statistic'?: number;
  'Missing Diff %': number;
}

interface PrivacyProxy {
  mean_real_to_real?: number | null;
  mean_real_to_synthetic?: number | null;
  min_real_to_real?: number | null;
  min_real_to_synthetic?: number | null;
  privacy_ratio?: number | null;
  note?: string;
}

interface Report {
  parameters: { epsilon: number; seed: number | null; strata_keys: string[]; n_rows_original: number; n_rows_synthetic: number };
  columns_dropped: string[];
  utility_metrics: Record<string, { total_variation_distance?: number; kolmogorov_smirnov?: number; missingness: { difference_pct: number } }>;
  privacy_proxy: PrivacyProxy;
  notes: string;
}

// ─── helpers ─────────────────────────────────────────────────────────────────

const ROLE_COLORS: Record<string, string> = {
  'Direct Identifier': 'bg-red-100 text-red-800',
  'Quasi-identifier':  'bg-yellow-100 text-yellow-800',
  'Sensitive':         'bg-orange-100 text-orange-800',
  'Non-sensitive':     'bg-green-100 text-green-800',
};

function RoleBadge({ role }: { role: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${ROLE_COLORS[role] ?? 'bg-gray-100 text-gray-700'}`}>
      {role}
    </span>
  );
}

function CheckBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className={`flex items-center gap-1 px-3 py-2 rounded text-sm font-medium ${ok ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
      <span>{ok ? '✓' : '✗'}</span>
      <span>{label}</span>
    </div>
  );
}

// ─── main component ───────────────────────────────────────────────────────────

function SyntheticDataInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { sessionId: ctxSid, datasetInfo } = useSession();
  const sid = searchParams.get('session_id') || ctxSid || '';

  // backend status
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  // step 1 — identification
  const [identifying, setIdentifying]     = useState(false);
  const [metadata, setMetadata]           = useState<ColumnMeta[] | null>(null);
  const [roleSummary, setRoleSummary]     = useState<Record<string, number>>({});
  const [identifySource, setIdentifySource] = useState('');
  const [identifyErr, setIdentifyErr]     = useState('');

  // step 2 — parameters
  const [epsilon, setEpsilon]             = useState(1.0);
  const [seed, setSeed]                   = useState(42);
  const [nSamples, setNSamples]           = useState(0);
  const [strataKeys, setStrataKeys]       = useState<string[]>([]);

  // step 3 — generation
  const [generating, setGenerating]       = useState(false);
  const [result, setResult]               = useState<GenerateResult | null>(null);
  const [genErr, setGenErr]               = useState('');

  // step 4 — report
  const [loadingReport, setLoadingReport] = useState(false);
  const [report, setReport]               = useState<Report | null>(null);
  const [reportErr, setReportErr]         = useState('');
  const [reportOpen, setReportOpen]       = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/`).then(r => setBackendOk(r.ok)).catch(() => setBackendOk(false));
  }, []);

  useEffect(() => {
    if (datasetInfo?.shape[0]) setNSamples(datasetInfo.shape[0]);
  }, [datasetInfo]);

  // available columns for strata selection (after identification)
  const availableCols: string[] = metadata
    ? metadata.filter(m => m.role !== 'Direct Identifier').map(m => m.column)
    : (datasetInfo?.columns ?? []);

  // ── api calls ──────────────────────────────────────────────────────────────

  const runIdentify = async () => {
    if (!sid) return;
    setIdentifying(true); setIdentifyErr(''); setMetadata(null);
    const fd = new FormData();
    fd.append('session_id', sid);
    try {
      const res = await fetch(`${API_BASE}/synthetic/identify`, { method: 'POST', body: fd });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error((d as { detail?: string }).detail || 'Identification failed'); }
      const data = await res.json();
      setMetadata(data.columns);
      setRoleSummary(data.role_summary ?? {});
      setIdentifySource(data.source ?? 'heuristic');
      // auto-suggest strata: district / sector / region
      const suggested = (data.columns as ColumnMeta[])
        .filter(c => /district|sector|region|province/i.test(c.column) && c.role !== 'Direct Identifier')
        .map(c => c.column);
      setStrataKeys(suggested);
    } catch (e: unknown) {
      setIdentifyErr(e instanceof Error ? e.message : 'Identification failed');
    } finally {
      setIdentifying(false);
    }
  };

  const generate = async () => {
    if (!sid) return;
    setGenerating(true); setGenErr(''); setResult(null); setReport(null);
    const fd = new FormData();
    fd.append('session_id', sid);
    fd.append('epsilon', String(epsilon));
    fd.append('seed', String(seed));
    fd.append('n_samples', String(nSamples));
    fd.append('strata_keys', JSON.stringify(strataKeys));
    try {
      const res = await fetch(`${API_BASE}/synthetic/generate-synthetic`, { method: 'POST', body: fd });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error((d as { detail?: string }).detail || 'Generation failed'); }
      setResult(await res.json());
    } catch (e: unknown) {
      setGenErr(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const fetchReport = async () => {
    if (!sid) return;
    setLoadingReport(true); setReportErr(''); setReportOpen(true);
    const fd = new FormData();
    fd.append('session_id', sid);
    try {
      const res = await fetch(`${API_BASE}/synthetic/report`, { method: 'POST', body: fd });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error((d as { detail?: string }).detail || 'Report failed'); }
      setReport(await res.json());
    } catch (e: unknown) {
      setReportErr(e instanceof Error ? e.message : 'Report generation failed');
    } finally {
      setLoadingReport(false);
    }
  };

  const download = async (format: 'csv' | 'excel') => {
    const res = await fetch(`${API_BASE}/synthetic/download-synthetic?session_id=${sid}&format=${format}`);
    if (!res.ok) { alert('Download failed'); return; }
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `synthetic_data.${format === 'excel' ? 'xlsx' : 'csv'}`;
    a.click();
  };

  // ── utility: build report table rows ──────────────────────────────────────

  const utilityRows: UtilityCol[] = report
    ? Object.entries(report.utility_metrics).map(([col, m]) => ({
        Column: col,
        ...(m.total_variation_distance !== undefined ? { TVD: +m.total_variation_distance.toFixed(4) } : {}),
        ...('kolmogorov_smirnov' in m && m.kolmogorov_smirnov !== undefined ? { 'KS Statistic': +m.kolmogorov_smirnov.toFixed(4) } : {}),
        'Missing Diff %': +m.missingness.difference_pct.toFixed(2),
      }))
    : [];

  if (!sid) return (
    <div className="page-container">
      <div className="alert-error">No session found. <a href="/" className="underline text-[#667eea]">Go home</a></div>
    </div>
  );

  return (
    <div className="page-container">
      <Breadcrumb />
      <div className="component-header">
        <h1>🎲 Synthetic Data Generation</h1>
        <p>Generate privacy-preserving synthetic data using Adaptive Permutation-Enhanced Differential Privacy (APEDP)</p>
      </div>

      <StatusBadge
        status={backendOk === null ? 'checking' : backendOk ? 'connected' : 'disconnected'}
        message={backendOk === null ? 'Checking backend…' : backendOk ? '✓ Backend connected' : '✗ Backend not connected'}
      />

      {/* ── Dataset Info ── */}
      <div className="section">
        <h2>📊 Dataset Information</h2>
        {datasetInfo ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-2">
            {[
              { label: 'Rows',    value: datasetInfo.shape[0] },
              { label: 'Columns', value: datasetInfo.shape[1] },
              { label: 'Session', value: sid.slice(0, 8) + '…' },
            ].map(({ label, value }) => (
              <div key={label} className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-[#667eea]">{value}</div>
                <div className="text-xs text-gray-500 mt-1">{label}</div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-500 mt-2">Session: {sid}</p>
        )}
      </div>

      {/* Original preview */}
      {datasetInfo?.sample_data?.length ? (
        <div className="section">
          <h2>📋 Original Data Preview</h2>
          <DataTable columns={datasetInfo.columns} rows={datasetInfo.sample_data} maxRows={5} />
        </div>
      ) : null}

      {/* ── Step 1: Identify ── */}
      <div className="section">
        <h2>🔍 Step 1: Column Identification</h2>
        <p className="text-sm text-gray-500 mt-1">
          Automatically classify each column as Direct Identifier, Quasi-identifier, Sensitive, or Non-sensitive.
          Direct Identifiers will be dropped before generation.
        </p>

        <button className="btn-primary mt-4" onClick={runIdentify} disabled={identifying}>
          {identifying ? 'Identifying…' : 'Run Identification'}
        </button>
        {identifyErr && <div className="alert-error mt-3">{identifyErr}</div>}

        {metadata && (
          <div className="mt-4">
            {/* Source label */}
            {identifySource && (
              <div className="mb-2 text-xs text-gray-500">
                Source: <span className={`font-semibold ${identifySource.includes('quasi') ? 'text-blue-600' : 'text-gray-600'}`}>
                  {identifySource === 'quasi-selection detection' ? '✓ Quasi-selection auto-detect results' :
                   identifySource === 'quasi-selection selection' ? '✓ Quasi-selection column selections' :
                   'Heuristic pattern matching'}
                </span>
              </div>
            )}
            {/* Role summary badges */}
            <div className="flex flex-wrap gap-2 mb-3">
              {Object.entries(roleSummary).map(([role, count]) => (
                <span key={role} className={`px-3 py-1 rounded-full text-xs font-semibold ${ROLE_COLORS[role] ?? 'bg-gray-100'}`}>
                  {role}: {count}
                </span>
              ))}
            </div>

            {/* Column classification table */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-gray-100 dark:bg-gray-700">
                    <th className="text-left p-2 border border-gray-200 dark:border-gray-600">Column</th>
                    <th className="text-left p-2 border border-gray-200 dark:border-gray-600">Dtype</th>
                    <th className="text-left p-2 border border-gray-200 dark:border-gray-600">Role</th>
                    <th className="text-left p-2 border border-gray-200 dark:border-gray-600">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {metadata.map(m => (
                    <tr key={m.column} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                      <td className="p-2 border border-gray-200 dark:border-gray-600 font-mono text-xs">{m.column}</td>
                      <td className="p-2 border border-gray-200 dark:border-gray-600 text-gray-500">{m.dtype}</td>
                      <td className="p-2 border border-gray-200 dark:border-gray-600"><RoleBadge role={m.role} /></td>
                      <td className="p-2 border border-gray-200 dark:border-gray-600">
                        <span className={m.action === 'Drop' ? 'text-red-600 font-semibold' : 'text-gray-600'}>{m.action}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ── Step 2: Parameters ── */}
      <div className="section">
        <h2>⚙️ Step 2: Synthesis Parameters</h2>
        <p className="text-sm text-gray-500 mt-1">
          Configure the differential privacy budget and generation settings.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mt-4">
          {/* Epsilon */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Epsilon (ε) &nbsp;<span className="text-gray-400 font-normal text-xs">Privacy budget — lower = more private</span>
            </label>
            <input
              type="number" min={0.01} max={10} step={0.1}
              value={epsilon}
              onChange={e => setEpsilon(parseFloat(e.target.value) || 1.0)}
              className="border border-gray-300 dark:border-gray-600 rounded p-2 w-full text-sm bg-white dark:bg-gray-800"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>0.01 (most private)</span><span>10 (most utility)</span>
            </div>
          </div>

          {/* Seed */}
          <div>
            <label className="block text-sm font-medium mb-1">Random Seed</label>
            <input
              type="number" min={0} step={1}
              value={seed}
              onChange={e => setSeed(parseInt(e.target.value) || 42)}
              className="border border-gray-300 dark:border-gray-600 rounded p-2 w-full text-sm bg-white dark:bg-gray-800"
            />
          </div>

          {/* n_samples */}
          <div>
            <label className="block text-sm font-medium mb-1">Number of Rows</label>
            <input
              type="number" min={10} step={10}
              value={nSamples}
              onChange={e => setNSamples(parseInt(e.target.value) || 100)}
              className="border border-gray-300 dark:border-gray-600 rounded p-2 w-full text-sm bg-white dark:bg-gray-800"
            />
          </div>

          {/* Strata keys */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Strata Keys &nbsp;<span className="text-gray-400 font-normal text-xs">Permutation groups</span>
            </label>
            <div className="border border-gray-300 dark:border-gray-600 rounded p-2 max-h-36 overflow-y-auto bg-white dark:bg-gray-800">
              {availableCols.length === 0 && (
                <p className="text-xs text-gray-400">Run identification first to see columns</p>
              )}
              {availableCols.map(col => (
                <label key={col} className="flex items-center gap-2 py-0.5 cursor-pointer text-sm">
                  <input
                    type="checkbox"
                    checked={strataKeys.includes(col)}
                    onChange={e => setStrataKeys(prev =>
                      e.target.checked ? [...prev, col] : prev.filter(k => k !== col)
                    )}
                  />
                  {col}
                </label>
              ))}
            </div>
            {strataKeys.length > 0 && (
              <p className="text-xs text-gray-500 mt-1">Selected: {strataKeys.join(', ')}</p>
            )}
          </div>
        </div>
      </div>

      {/* ── Step 3: Generate ── */}
      <div className="section">
        <h2>🧬 Step 3: Generate Synthetic Data</h2>

        <button className="btn-primary mt-2" onClick={generate} disabled={generating}>
          {generating ? 'Generating…' : 'Generate Synthetic Data'}
        </button>
        {genErr && <div className="alert-error mt-3">{genErr}</div>}

        {result && (
          <div className="mt-4">
            <div className="alert-success mb-4">✓ Synthetic data generated successfully!</div>

            {/* Shape summary */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              {[
                { label: 'Original Rows',   value: result.original_shape[0] },
                { label: 'Original Cols',   value: result.original_shape[1] },
                { label: 'Synthetic Rows',  value: result.synthetic_shape[0] },
                { label: 'Synthetic Cols',  value: result.synthetic_shape[1] },
              ].map(({ label, value }) => (
                <div key={label} className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-center">
                  <div className="text-xl font-bold text-[#667eea]">{value}</div>
                  <div className="text-xs text-gray-500 mt-1">{label}</div>
                </div>
              ))}
            </div>

            {/* Dropped columns */}
            {result.dropped_columns.length > 0 && (
              <div className="alert-error mb-3 text-sm">
                <strong>Dropped (Direct Identifiers):</strong> {result.dropped_columns.join(', ')}
              </div>
            )}

            {/* Self-check */}
            <div className="mb-4">
              <h3 className="text-sm font-semibold mb-2">Self-Check</h3>
              <div className="flex flex-wrap gap-2">
                <CheckBadge ok={result.self_check.no_direct_identifiers} label="No Direct IDs" />
                <CheckBadge ok={result.self_check.row_count_match}       label="Row Count Match" />
                <CheckBadge ok={result.self_check.no_nan_explosion}      label="No NaN Explosion" />
                <CheckBadge ok={result.self_check.epsilon_valid}         label="ε Valid" />
              </div>
            </div>

            {/* Preview */}
            <h3 className="text-sm font-semibold mb-2">Synthetic Data Preview (first 20 rows)</h3>
            <DataTable columns={result.columns} rows={result.sample_data} maxRows={20} />

            {/* Downloads */}
            <div className="flex gap-3 mt-4 flex-wrap">
              <button className="btn-success" onClick={() => download('csv')}>⬇ Download CSV</button>
              <button className="btn-info"    onClick={() => download('excel')}>⬇ Download Excel</button>
            </div>
          </div>
        )}
      </div>

      {/* ── Step 4: Quality Report ── */}
      {result && (
        <div className="section">
          <h2>📊 Step 4: Quality Report</h2>
          <p className="text-sm text-gray-500 mt-1">
            Utility metrics (TVD / KS statistic) and nearest-neighbour privacy proxy comparing original vs synthetic.
          </p>

          <button className="btn-secondary mt-3" onClick={fetchReport} disabled={loadingReport}>
            {loadingReport ? 'Generating report…' : reportOpen ? 'Refresh Report' : 'Generate Quality Report'}
          </button>
          {reportErr && <div className="alert-error mt-3">{reportErr}</div>}

          {report && reportOpen && (
            <div className="mt-4 space-y-6">

              {/* Parameters */}
              <div>
                <h3 className="text-sm font-semibold mb-2">Parameters Used</h3>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                  {[
                    { label: 'ε (Epsilon)',     value: report.parameters.epsilon },
                    { label: 'Seed',            value: report.parameters.seed ?? '—' },
                    { label: 'Original Rows',   value: report.parameters.n_rows_original },
                    { label: 'Synthetic Rows',  value: report.parameters.n_rows_synthetic },
                    { label: 'Strata Keys',     value: report.parameters.strata_keys.join(', ') || 'None' },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-gray-50 dark:bg-gray-800 rounded p-2 text-center text-sm">
                      <div className="font-semibold">{value}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{label}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Utility Metrics table */}
              {utilityRows.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-2">Utility Metrics</h3>
                  <p className="text-xs text-gray-400 mb-2">
                    TVD (categorical): closer to 0 = better · KS (numeric): closer to 0 = better
                  </p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="bg-gray-100 dark:bg-gray-700">
                          {Object.keys(utilityRows[0]).map(h => (
                            <th key={h} className="text-left p-2 border border-gray-200 dark:border-gray-600">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {utilityRows.map(row => (
                          <tr key={row.Column} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                            {Object.values(row).map((v, i) => (
                              <td key={i} className="p-2 border border-gray-200 dark:border-gray-600 font-mono text-xs">{String(v ?? '—')}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Averages */}
                  <div className="flex flex-wrap gap-4 mt-3">
                    {['TVD', 'KS Statistic'].map(metric => {
                      const vals = utilityRows.map(r => (r as Record<string, number | string>)[metric] as number).filter(v => typeof v === 'number');
                      if (!vals.length) return null;
                      const avg = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(4);
                      return (
                        <div key={metric} className="bg-blue-50 dark:bg-blue-900/30 rounded px-4 py-2 text-sm">
                          <span className="font-medium">Avg {metric}:</span> <span className="font-mono">{avg}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Privacy Proxy */}
              <div>
                <h3 className="text-sm font-semibold mb-2">Privacy Proxy — Nearest-Neighbour Analysis</h3>
                {report.privacy_proxy.note ? (
                  <p className="text-sm text-gray-400">{report.privacy_proxy.note}</p>
                ) : report.privacy_proxy.privacy_ratio != null ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    {[
                      { label: 'Mean Distance (Real → Real)',      value: report.privacy_proxy.mean_real_to_real?.toFixed(4) },
                      { label: 'Mean Distance (Real → Synthetic)', value: report.privacy_proxy.mean_real_to_synthetic?.toFixed(4) },
                      { label: 'Privacy Ratio',                    value: report.privacy_proxy.privacy_ratio?.toFixed(4) },
                    ].map(({ label, value }) => (
                      <div key={label} className="bg-purple-50 dark:bg-purple-900/30 rounded p-3 text-center text-sm">
                        <div className="text-lg font-bold text-purple-700 dark:text-purple-300">{value ?? '—'}</div>
                        <div className="text-xs text-gray-500 mt-1">{label}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">Privacy proxy not available (requires numeric columns).</p>
                )}
              </div>

              {/* Notes */}
              <p className="text-xs text-gray-400 italic">{report.notes}</p>
            </div>
          )}
        </div>
      )}

      {/* ── Navigation ── */}
      <div className="section">
        <h3>Other Components</h3>
        <div className="flex gap-3 flex-wrap mt-2">
          <button className="btn-secondary" onClick={() => router.push(`/quasi-selection?session_id=${sid}`)}>Quasi-Selection</button>
          <button className="btn-secondary" onClick={() => router.push(`/anonymization?session_id=${sid}`)}>Anonymization</button>
          <button className="btn-secondary" onClick={() => router.push(`/reidentification?session_id=${sid}`)}>Re-identification Risk</button>
          <button className="btn-secondary" onClick={() => router.push('/')}>Home</button>
        </div>
      </div>
    </div>
  );
}

export default function SyntheticDataPage() {
  return (
    <Suspense fallback={<div className="page-container"><p>Loading…</p></div>}>
      <SyntheticDataInner />
    </Suspense>
  );
}
