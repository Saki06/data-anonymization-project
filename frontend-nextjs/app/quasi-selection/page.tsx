'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useSession, API_BASE } from '@/lib/SessionContext';
import Breadcrumb from '@/components/Breadcrumb';
import StatusBadge from '@/components/StatusBadge';
import DataTable from '@/components/DataTable';
import RiskValidationTab from './RiskValidationTab';
import ReportsTab from './ReportsTab';

interface DetectDetail {
  column_name: string;
  class: 'DIRECT_IDENTIFIER' | 'QUASI_IDENTIFIER' | 'SENSITIVE' | 'NON_SENSITIVE';
  confidence: number;
  reasons: string;
}

interface DetectResult {
  details: DetectDetail[];
  quasi_identifiers: string[];
  sensitive_attributes: string[];
}

interface RiskCombo { qi_cols: string; comb_size: number; k_min: number; unique_pct: number; total_groups: number; avg_group_size: number; max_group_size: number; unique_groups: number; risk_level: string; }

const CLASS_BADGE: Record<string, string> = {
  DIRECT_IDENTIFIER: 'bg-red-100 text-red-700',
  QUASI_IDENTIFIER:  'bg-yellow-100 text-yellow-800',
  SENSITIVE:         'bg-orange-100 text-orange-700',
  NON_SENSITIVE:     'bg-green-100 text-green-700',
};

const TABS = ['📋 Data Overview', '🏷️ Classification', '⚠️ Risk Validation', '📄 Reports'] as const;

function QuasiSelectionInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { sessionId: ctxSid, datasetInfo, setQuasiIdentifiers } = useSession();

  const sid = searchParams.get('session_id') || ctxSid || '';
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [columns, setColumns] = useState<string[]>(datasetInfo?.columns ?? []);
  const [sampleData, setSampleData] = useState(datasetInfo?.sample_data ?? []);
  const [shape, setShape] = useState(datasetInfo?.shape ?? [0, 0]);

  // Tabs
  const [activeTab, setActiveTab] = useState(0);

  // Auto-detect state
  const [detecting, setDetecting] = useState(false);
  const [detectResult, setDetectResult] = useState<DetectResult | null>(null);
  const [classMap, setClassMap] = useState<Record<string, string>>({});
  const [showTable, setShowTable] = useState(true);

  // Manual selection
  const [selectedQIs, setSelectedQIs] = useState<Set<string>>(new Set());
  const [selectedSens, setSelectedSens] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  // Risk combos (shared between Risk Validation & Reports tabs)
  const [riskCombos, setRiskCombos] = useState<RiskCombo[]>([]);

  // Dataset extra stats
  const [missingCells, setMissingCells] = useState(0);
  const [duplicateRows, setDuplicateRows] = useState(0);
  const [profilingData, setProfilingData] = useState<Record<string,any>[]>([]);

  useEffect(() => {
    fetch(`${API_BASE}/`).then(r => setBackendOk(r.ok)).catch(() => setBackendOk(false));
  }, []);

  useEffect(() => {
    if (!sid) return;
    if (columns.length) return;
    fetch(`${API_BASE}/session/${sid}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setColumns(data.columns ?? []);
          setSampleData(data.sample_data ?? []);
          setShape(data.shape ?? [0, 0]);
          if (data.quasi_identifiers?.length) setSelectedQIs(new Set(data.quasi_identifiers));
          if (data.sensitive_attributes?.length) setSelectedSens(new Set(data.sensitive_attributes));
          if (data.missing_cells !== undefined) setMissingCells(data.missing_cells);
          if (data.duplicate_rows !== undefined) setDuplicateRows(data.duplicate_rows);
          if (data.profiling) setProfilingData(data.profiling);
        }
      })
      .catch(() => {});
  }, [sid, columns.length]);

  const runAutoDetect = async () => {
    if (!sid) return;
    setDetecting(true);
    const fd = new FormData();
    fd.append('session_id', sid);
    try {
      const res = await fetch(`${API_BASE}/auto-detect-columns`, { method: 'POST', body: fd });
      if (!res.ok) throw new Error((await res.json()).detail || 'Auto-detect failed');
      const data: DetectResult = await res.json();
      setDetectResult(data);
      const map: Record<string, string> = {};
      data.details.forEach(d => { map[d.column_name] = d.class; });
      setClassMap(map);
      setSelectedQIs(new Set(data.quasi_identifiers));
      setSelectedSens(new Set(data.sensitive_attributes));
    } catch (e: unknown) {
      alert('Auto-detect error: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setDetecting(false);
    }
  };

  const applyOverrides = () => {
    const qis  = Object.entries(classMap).filter(([, v]) => v === 'QUASI_IDENTIFIER').map(([k]) => k);
    const sens = Object.entries(classMap).filter(([, v]) => v === 'SENSITIVE').map(([k]) => k);
    setSelectedQIs(new Set(qis));
    setSelectedSens(new Set(sens));
  };

  const toggleQI = (col: string) => {
    setSelectedQIs(prev => { const s = new Set(prev); s.has(col) ? s.delete(col) : s.add(col); return s; });
  };
  const toggleSens = (col: string) => {
    setSelectedSens(prev => { const s = new Set(prev); s.has(col) ? s.delete(col) : s.add(col); return s; });
  };

  const confirmSelection = async () => {
    const qis  = Array.from(selectedQIs);
    const sens = Array.from(selectedSens);
    if (!qis.length) { alert('Please select at least one quasi-identifier.'); return; }
    setSaving(true);
    const fd = new FormData();
    fd.append('session_id', sid);
    fd.append('quasi_identifiers', JSON.stringify(qis));
    if (sens.length) fd.append('sensitive_attributes', JSON.stringify(sens));
    try {
      const res = await fetch(`${API_BASE}/select-quasi-identifiers`, { method: 'POST', body: fd });
      if (!res.ok) throw new Error('Failed to save selection');
      setQuasiIdentifiers(qis, sens);
      router.push(`/anonymization?session_id=${sid}&quasi_identifiers=${encodeURIComponent(JSON.stringify(qis))}&sensitive_attributes=${encodeURIComponent(JSON.stringify(sens))}`);
    } catch (e: unknown) {
      alert('Error: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  };

  const countByClass = (cls: string) => Object.values(classMap).filter(v => v === cls).length;

  // Derived lists for Risk & Reports tabs
  const quasiCandidates = Object.entries(classMap).filter(([,v])=>v==='QUASI_IDENTIFIER').map(([k])=>k);
  const sensitiveCandidates = Object.entries(classMap).filter(([,v])=>v==='SENSITIVE').map(([k])=>k);

  // Classification summary for charts
  const classSummary = Object.entries(
    (detectResult?.details ?? []).reduce<Record<string,number>>((acc,d) => { const c = classMap[d.column_name] ?? d.class; acc[c]=(acc[c]||0)+1; return acc; }, {})
  );
  const maxClassCount = Math.max(...classSummary.map(([,v])=>v), 1);

  if (!sid) {
    return (
      <div className="page-container">
        <div className="alert-error">No session found. <a href="/" className="underline text-blue-600 dark:text-blue-400">Go to home</a></div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <Breadcrumb />
      <div className="component-header">
        <div>
          <h1>🎯 Quasi-Identifier Selection</h1>
          <p>Auto-detect column types with the HIES NLP pipeline, then fine-tune before anonymization</p>
        </div>
      </div>

      <StatusBadge
        status={backendOk === null ? 'checking' : backendOk ? 'connected' : 'disconnected'}
        message={backendOk === null ? 'Checking backend…' : backendOk ? '✓ Backend connected' : '✗ Backend not connected'}
      />

      {/* Dataset Info */}
      <div className="section">
        <h2>📊 Dataset Information</h2>
        <p><strong>Session ID:</strong> {sid}</p>
        <p><strong>Records:</strong> {shape[0]} &nbsp;|&nbsp; <strong>Columns:</strong> {shape[1] || columns.length}</p>
      </div>

      {/* Tab Bar */}
      <div className="tab-bar">
        {TABS.map((tab, i) => (
          <button key={tab} className={`tab-btn ${activeTab === i ? 'active' : ''}`} onClick={() => setActiveTab(i)}>
            {tab}
          </button>
        ))}
      </div>

      {/* ===== Tab 0: Data Overview ===== */}
      {activeTab === 0 && (
        <div className="space-y-6">
          <div className="section">
            <h3>Dataset Summary</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
              <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-slate-400">Rows</p>
                <p className="text-2xl font-bold text-slate-800 dark:text-slate-200">{shape[0]}</p>
              </div>
              <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-slate-400">Columns</p>
                <p className="text-2xl font-bold text-slate-800 dark:text-slate-200">{shape[1] || columns.length}</p>
              </div>
              <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-slate-400">Missing Cells</p>
                <p className="text-2xl font-bold text-slate-800 dark:text-slate-200">{missingCells}</p>
              </div>
              <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-slate-400">Duplicate Rows</p>
                <p className="text-2xl font-bold text-slate-800 dark:text-slate-200">{duplicateRows}</p>
              </div>
            </div>
          </div>

          {/* Column Profiling */}
          {profilingData.length > 0 && (
            <div className="section">
              <h3>Column Profiling</h3>
              <div className="overflow-x-auto">
                <table className="data-table"><thead><tr>
                  {Object.keys(profilingData[0]).map(k => <th key={k}>{k}</th>)}
                </tr></thead><tbody>
                  {profilingData.map((row, i) => (
                    <tr key={i}>{Object.values(row).map((v, j) => <td key={j}>{String(v)}</td>)}</tr>
                  ))}
                </tbody></table>
              </div>
            </div>
          )}

          {/* Data Preview */}
          {columns.length > 0 && sampleData.length > 0 && (
            <div className="section">
              <h3>Data Preview</h3>
              <DataTable columns={columns} rows={sampleData} maxRows={10} />
            </div>
          )}
        </div>
      )}

      {/* ===== Tab 1: Classification ===== */}
      {activeTab === 1 && (
        <div className="space-y-6">
          {/* Auto-Detect */}
          <div className="section">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h3 className="mb-0">🔍 Auto-Detect Column Types</h3>
              {detectResult && (
                <button className="text-blue-600 dark:text-blue-400 text-sm underline" onClick={() => setShowTable(prev => !prev)}>
                  {showTable ? 'Hide' : 'Show'} table
                </button>
              )}
            </div>
            <p className="text-sm text-gray-500 dark:text-slate-400 mt-1">
              Uses keyword matching, regex patterns and semantic heuristics to automatically classify every column.
            </p>

            <button className="btn-primary mt-3" onClick={runAutoDetect} disabled={detecting || !sid}>
              {detecting ? '⏳ Detecting…' : '🔍 Run Auto-Detection'}
            </button>

            {detectResult && (
              <>
                {/* Summary Badges */}
                <div className="flex flex-wrap gap-3 mt-4">
                  <span className="badge bg-red-100 text-red-700">🔴 Direct IDs: {countByClass('DIRECT_IDENTIFIER')}</span>
                  <span className="badge bg-yellow-100 text-yellow-800">🟡 Quasi IDs: {countByClass('QUASI_IDENTIFIER')}</span>
                  <span className="badge bg-orange-100 text-orange-700">🟠 Sensitive: {countByClass('SENSITIVE')}</span>
                  <span className="badge bg-green-100 text-green-700">🟢 Non-Sensitive: {countByClass('NON_SENSITIVE')}</span>
                </div>

                {/* Classification Summary Chart */}
                {classSummary.length > 0 && (
                  <div className="mt-4">
                    <h3>Class Distribution</h3>
                    <div className="space-y-2 mt-2">
                      {classSummary.map(([label, count]) => (
                        <div key={label} className="flex items-center gap-3">
                          <span className="text-xs w-36 truncate text-slate-600 dark:text-slate-400">{label}</span>
                          <div className="flex-1 h-6 bg-gray-200 dark:bg-slate-700 rounded overflow-hidden">
                            <div className={`h-full rounded transition-all ${CLASS_BADGE[label]?.split(' ')[0] || 'bg-blue-400'}`} style={{ width: `${(count / maxClassCount) * 100}%` }} />
                          </div>
                          <span className="text-sm font-bold w-8 text-right text-slate-700 dark:text-slate-300">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Classification Table */}
                {showTable && (
                  <div className="overflow-x-auto mt-4">
                    <p className="text-sm bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700/40 text-yellow-800 dark:text-yellow-300 p-2 rounded mb-2">
                      💡 Auto-detected classes are pre-filled. Use the dropdowns to override, then click <strong>Apply Overrides</strong>.
                    </p>
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="bg-blue-50 dark:bg-slate-700">
                          <th className="p-2 text-left border-b-2 border-gray-300 dark:border-slate-500 text-slate-700 dark:text-slate-200">Column</th>
                          <th className="p-2 text-left border-b-2 border-gray-300 dark:border-slate-500 text-slate-700 dark:text-slate-200">Auto Class</th>
                          <th className="p-2 text-left border-b-2 border-gray-300 dark:border-slate-500 text-slate-700 dark:text-slate-200">Override</th>
                          <th className="p-2 text-left border-b-2 border-gray-300 dark:border-slate-500 text-slate-700 dark:text-slate-200">Confidence</th>
                          <th className="p-2 text-left border-b-2 border-gray-300 dark:border-slate-500 text-slate-700 dark:text-slate-200">Reasons</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detectResult.details.map((row) => {
                          const pct = Math.round((row.confidence || 0) * 100);
                          const current = classMap[row.column_name] ?? row.class;
                          return (
                            <tr key={row.column_name} className="hover:bg-gray-50 dark:hover:bg-slate-700/50 border-b border-gray-100 dark:border-slate-700">
                              <td className="p-2 font-semibold text-slate-800 dark:text-slate-200">{row.column_name}</td>
                              <td className="p-2"><span className={`badge ${CLASS_BADGE[row.class] ?? ''}`}>{row.class}</span></td>
                              <td className="p-2">
                                <select
                                  className="text-xs border border-gray-200 dark:border-slate-500 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-200 rounded px-1 py-0.5"
                                  value={current}
                                  onChange={(e) => setClassMap(prev => ({ ...prev, [row.column_name]: e.target.value }))}
                                >
                                  {['DIRECT_IDENTIFIER','QUASI_IDENTIFIER','SENSITIVE','NON_SENSITIVE'].map(c => (
                                    <option key={c} value={c}>{c}</option>
                                  ))}
                                </select>
                              </td>
                              <td className="p-2">
                                <div className="flex items-center gap-1">
                                  <div className="w-20 h-1.5 bg-gray-200 dark:bg-slate-600 rounded overflow-hidden">
                                    <div className="h-full bg-blue-400 dark:bg-blue-500 rounded" style={{ width: `${pct}%` }} />
                                  </div>
                                  <span className="text-xs text-gray-500 dark:text-slate-400">{pct}%</span>
                                </div>
                              </td>
                              <td className="p-2 text-xs text-gray-500 dark:text-slate-400">{row.reasons}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    <button className="btn-primary mt-3" onClick={applyOverrides}>✅ Apply Overrides &amp; Pre-fill Selection</button>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Manual Selection */}
          {columns.length > 0 && (
            <div className="section">
              <h3>🎯 Select Quasi-Identifiers &amp; Sensitive Attributes</h3>
              <p className="text-sm text-gray-500 dark:text-slate-400">Check the columns to use. Auto-detection pre-ticks the suggested ones.</p>

              <div className="mt-4">
                <h3>Quasi-Identifiers <span className="text-xs text-gray-400 dark:text-slate-500">(Required — at least one)</span></h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
                  {columns.map(col => (
                    <label key={col} className="flex items-center gap-2 p-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded cursor-pointer hover:border-blue-500 dark:hover:border-blue-400 hover:bg-blue-50 dark:hover:bg-slate-700 transition-colors">
                      <input type="checkbox" checked={selectedQIs.has(col)} onChange={() => toggleQI(col)} className="accent-blue-600 dark:accent-blue-400 w-4 h-4" />
                      <span className="text-sm text-slate-700 dark:text-slate-300">{col}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="mt-5">
                <h3>Sensitive Attributes <span className="text-xs text-gray-400 dark:text-slate-500">(Optional)</span></h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
                  {columns.map(col => (
                    <label key={col} className="flex items-center gap-2 p-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded cursor-pointer hover:border-blue-500 dark:hover:border-blue-400 hover:bg-blue-50 dark:hover:bg-slate-700 transition-colors">
                      <input type="checkbox" checked={selectedSens.has(col)} onChange={() => toggleSens(col)} className="accent-blue-600 dark:accent-blue-400 w-4 h-4" />
                      <span className="text-sm text-slate-700 dark:text-slate-300">{col}</span>
                    </label>
                  ))}
                </div>
              </div>

              <button className="btn-primary mt-5" onClick={confirmSelection} disabled={saving || selectedQIs.size === 0}>
                {saving ? 'Saving…' : 'Confirm Selection & Proceed to Anonymization'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* ===== Tab 2: Risk Validation ===== */}
      {activeTab === 2 && (
        <RiskValidationTab
          sid={sid}
          quasiCandidates={quasiCandidates.length > 0 ? quasiCandidates : Array.from(selectedQIs)}
          sensitiveCandidates={sensitiveCandidates.length > 0 ? sensitiveCandidates : Array.from(selectedSens)}
        />
      )}

      {/* ===== Tab 3: Reports ===== */}
      {activeTab === 3 && (
        <ReportsTab
          sid={sid}
          classDetails={detectResult?.details ?? []}
          riskCombos={riskCombos}
          datasetShape={shape as [number, number]}
        />
      )}

      {/* Navigation */}
      <div className="section">
        <h3>Other Components</h3>
        <div className="flex gap-3 flex-wrap mt-2">
          <button className="btn-secondary" onClick={() => router.push(`/synthetic-data?session_id=${sid}`)}>Synthetic Data</button>
          <button className="btn-secondary" onClick={() => router.push(`/reidentification?session_id=${sid}`)}>Re-identification</button>
          <button className="btn-secondary" onClick={() => router.push('/')}>Back to Home</button>
        </div>
      </div>
    </div>
  );
}

export default function QuasiSelectionPage() {
  return <Suspense fallback={<div className="page-container"><p>Loading…</p></div>}><QuasiSelectionInner /></Suspense>;
}
