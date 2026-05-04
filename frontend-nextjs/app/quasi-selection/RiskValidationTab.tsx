'use client';
import { useState } from 'react';
import { API_BASE } from '@/lib/SessionContext';

interface RiskCombo { qi_cols: string; comb_size: number; k_min: number; unique_pct: number; total_groups: number; avg_group_size: number; max_group_size: number; unique_groups: number; risk_level: string; }
interface DetailedEvidence { qi_columns: string[]; k_min: number; unique_pct: number; risk_level: string; total_groups: number; unique_groups: number; records_in_unique_groups: number; avg_group_size: number; max_group_size: number; total_records: number; group_size_distribution: Record<string,number>; risky_groups: Record<string,any>[]; }
interface LDivResult { sensitive_attribute: string; min_l_diversity: number; details: Record<string,any>[]; }

const RISK_COLOR: Record<string,string> = { CRITICAL:'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300', HIGH:'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300', MEDIUM:'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300', LOW:'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' };

export default function RiskValidationTab({ sid, quasiCandidates, sensitiveCandidates }: { sid: string; quasiCandidates: string[]; sensitiveCandidates: string[]; }) {
  const [selectedQIs, setSelectedQIs] = useState<string[]>(quasiCandidates.slice(0,3));
  const [maxComb, setMaxComb] = useState(3);
  const [searching, setSearching] = useState(false);
  const [combos, setCombos] = useState<RiskCombo[]>([]);
  const [chosenCombo, setChosenCombo] = useState('');
  const [evidence, setEvidence] = useState<DetailedEvidence|null>(null);
  const [loadingEvidence, setLoadingEvidence] = useState(false);
  const [sensCol, setSensCol] = useState(sensitiveCandidates[0]||'');
  const [ldiv, setLdiv] = useState<LDivResult|null>(null);
  const [loadingLdiv, setLoadingLdiv] = useState(false);

  const toggleQI = (col:string) => setSelectedQIs(prev => prev.includes(col) ? prev.filter(c=>c!==col) : [...prev, col]);

  const runSearch = async () => {
    if(!selectedQIs.length){alert('Select at least one QI column.');return;}
    setSearching(true); setCombos([]); setEvidence(null); setLdiv(null);
    const fd = new FormData();
    fd.append('session_id', sid);
    fd.append('quasi_identifiers', JSON.stringify(selectedQIs));
    fd.append('max_comb_size', String(maxComb));
    try {
      const res = await fetch(`${API_BASE}/search-qi-combinations`,{method:'POST',body:fd});
      if(!res.ok) throw new Error((await res.json()).detail||'Search failed');
      const data = await res.json();
      setCombos(data.combinations||[]);
      if(data.combinations?.length) setChosenCombo(data.combinations[0].qi_cols);
    } catch(e:any){alert(e.message);}
    finally{setSearching(false);}
  };

  const loadEvidence = async (qiStr:string) => {
    setChosenCombo(qiStr); setLoadingEvidence(true); setEvidence(null); setLdiv(null);
    const fd = new FormData();
    fd.append('session_id', sid);
    fd.append('qi_columns', qiStr);
    try {
      const res = await fetch(`${API_BASE}/detailed-risk-evidence`,{method:'POST',body:fd});
      if(res.ok) setEvidence(await res.json());
    } catch{}
    finally{setLoadingEvidence(false);}
  };

  const loadLDiv = async () => {
    if(!sensCol||!chosenCombo) return;
    setLoadingLdiv(true);
    const fd = new FormData();
    fd.append('session_id', sid);
    fd.append('quasi_identifiers', JSON.stringify(chosenCombo.split(',').map(s=>s.trim())));
    fd.append('sensitive_column', sensCol);
    try {
      const res = await fetch(`${API_BASE}/compute-l-diversity`,{method:'POST',body:fd});
      if(res.ok) setLdiv(await res.json());
    } catch{}
    finally{setLoadingLdiv(false);}
  };

  const maxBarVal = combos.length ? Math.max(...combos.slice(0,10).map(c=>c.unique_pct),1) : 1;
  const bestBySize = combos.length ? Array.from(new Set(combos.map(c=>c.comb_size))).sort().map(s=>combos.find(c=>c.comb_size===s)!).filter(Boolean) : [];

  return (
    <div className="space-y-6">
      {/* QI Selection */}
      <div className="section">
        <h3>Select Quasi-Identifier Columns</h3>
        <p className="text-sm text-gray-500 dark:text-slate-400">Select QI attributes to evaluate disclosure risk.</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
          {quasiCandidates.map(col=>(
            <label key={col} className="flex items-center gap-2 p-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded cursor-pointer hover:border-blue-500 transition-colors">
              <input type="checkbox" checked={selectedQIs.includes(col)} onChange={()=>toggleQI(col)} className="accent-blue-600 w-4 h-4"/>
              <span className="text-sm text-slate-700 dark:text-slate-300">{col}</span>
            </label>
          ))}
        </div>
        {quasiCandidates.length===0 && <p className="text-sm text-amber-600 mt-2">No QUASI columns detected. Run auto-detection first.</p>}
        <div className="flex items-center gap-4 mt-4">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Max combination size:</label>
          <input type="range" min={1} max={4} value={maxComb} onChange={e=>setMaxComb(+e.target.value)} className="w-32"/>
          <span className="text-sm font-bold text-blue-600">{maxComb}</span>
        </div>
        <button className="btn-primary mt-4" onClick={runSearch} disabled={searching||!selectedQIs.length}>
          {searching?'⏳ Searching…':'🔍 Run Risk Search'}
        </button>
      </div>

      {/* Ranked Results */}
      {combos.length>0 && (
        <div className="section">
          <h3>Ranked Quasi-Identifier Combination Results</h3>
          <div className="overflow-x-auto"><table className="data-table"><thead><tr>
            <th>QI Columns</th><th>Size</th><th>k-min</th><th>Unique %</th><th>Groups</th><th>Avg Size</th><th>Risk</th>
          </tr></thead><tbody>
            {combos.map((c,i)=>(
              <tr key={i} className="cursor-pointer" onClick={()=>loadEvidence(c.qi_cols)}>
                <td className="font-medium">{c.qi_cols}</td><td>{c.comb_size}</td><td>{c.k_min}</td>
                <td>{c.unique_pct}%</td><td>{c.total_groups}</td><td>{c.avg_group_size}</td>
                <td><span className={`badge ${RISK_COLOR[c.risk_level]||''}`}>{c.risk_level}</span></td>
              </tr>
            ))}
          </tbody></table></div>

          {/* Bar Chart */}
          <h3 className="mt-6">Top Risky QI Combinations</h3>
          <div className="space-y-2 mt-2">
            {combos.slice(0,10).map((c,i)=>(
              <div key={i} className="flex items-center gap-3">
                <span className="text-xs w-40 truncate text-slate-600 dark:text-slate-400">{c.qi_cols}</span>
                <div className="flex-1 h-5 bg-gray-200 dark:bg-slate-700 rounded overflow-hidden">
                  <div className="h-full bg-blue-500 rounded transition-all" style={{width:`${(c.unique_pct/maxBarVal)*100}%`}}/>
                </div>
                <span className="text-xs w-14 text-right text-slate-600 dark:text-slate-400">{c.unique_pct}%</span>
              </div>
            ))}
          </div>

          {/* Highest Risk */}
          <h3 className="mt-6">Highest-Risk Combination</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-2">
            <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">Best k-min</p><p className="text-2xl font-bold text-slate-800 dark:text-slate-200">{combos[0].k_min}</p></div>
            <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">Unique %</p><p className="text-2xl font-bold text-slate-800 dark:text-slate-200">{combos[0].unique_pct}%</p></div>
            <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">QI Set</p><p className="text-sm font-semibold text-slate-700 dark:text-slate-300 break-all">{combos[0].qi_cols}</p></div>
            <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">Risk Level</p><p className="text-2xl font-bold"><span className={`badge ${RISK_COLOR[combos[0].risk_level]||''}`}>{combos[0].risk_level}</span></p></div>
          </div>

          {/* Best by Size */}
          {bestBySize.length>1 && (<>
            <h3 className="mt-6">Best by Combination Size</h3>
            <div className="space-y-2 mt-2">
              {bestBySize.map(b=>(
                <div key={b.comb_size} className="flex items-center gap-3 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded p-3">
                  <span className="font-semibold text-sm text-blue-600">{b.comb_size}-attr</span>
                  <span className="text-sm text-slate-700 dark:text-slate-300 flex-1">{b.qi_cols}</span>
                  <span className="text-xs text-gray-500">k={b.k_min} | {b.unique_pct}%</span>
                  <span className={`badge ${RISK_COLOR[b.risk_level]||''}`}>{b.risk_level}</span>
                </div>
              ))}
            </div>
          </>)}

          {/* Detailed Evidence */}
          <h3 className="mt-6">Detailed Evidence for Selected Combination</h3>
          <select className="border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm rounded px-3 py-2 mt-2" value={chosenCombo} onChange={e=>{setChosenCombo(e.target.value);loadEvidence(e.target.value);}}>
            {combos.map(c=><option key={c.qi_cols} value={c.qi_cols}>{c.qi_cols}</option>)}
          </select>

          {loadingEvidence && <p className="text-sm text-gray-500 mt-2">Loading evidence…</p>}
          {evidence && (
            <div className="mt-4 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">Min k-anonymity</p><p className="text-2xl font-bold">{evidence.k_min}</p></div>
                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">Unique %</p><p className="text-2xl font-bold">{evidence.unique_pct}%</p></div>
                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">Risk Level</p><p className="text-xl font-bold"><span className={`badge ${RISK_COLOR[evidence.risk_level]||''}`}>{evidence.risk_level}</span></p></div>
                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">Equivalence Classes</p><p className="text-2xl font-bold">{evidence.total_groups}</p></div>
                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">Avg Group Size</p><p className="text-2xl font-bold">{evidence.avg_group_size}</p></div>
                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4"><p className="text-xs text-gray-500">Max Group Size</p><p className="text-2xl font-bold">{evidence.max_group_size}</p></div>
              </div>

              <div className="text-sm text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded p-3">
                <p><strong>Selected QI:</strong> {evidence.qi_columns.join(', ')}</p>
                <p><strong>Unique groups:</strong> {evidence.unique_groups} | <strong>Records in unique groups:</strong> {evidence.records_in_unique_groups}</p>
              </div>

              {/* Risky Groups Table */}
              {evidence.risky_groups.length>0 && (<>
                <h3>Top Risky Equivalence Groups</h3>
                <div className="overflow-x-auto"><table className="data-table"><thead><tr>
                  {Object.keys(evidence.risky_groups[0]).filter(k=>k!=='equivalence_class').map(k=><th key={k}>{k}</th>)}
                </tr></thead><tbody>
                  {evidence.risky_groups.map((g,i)=>(
                    <tr key={i}>{Object.entries(g).filter(([k])=>k!=='equivalence_class').map(([k,v])=><td key={k}>{String(v)}</td>)}</tr>
                  ))}
                </tbody></table></div>
              </>)}

              {/* Group Size Distribution */}
              {Object.keys(evidence.group_size_distribution).length>0 && (<>
                <h3>Group Size Distribution</h3>
                <div className="space-y-1 mt-2">
                  {(()=>{const entries=Object.entries(evidence.group_size_distribution).map(([k,v])=>[+k,v] as [number,number]); const mx=Math.max(...entries.map(e=>e[1]),1); return entries.slice(0,20).map(([sz,cnt])=>(
                    <div key={sz} className="flex items-center gap-2">
                      <span className="text-xs w-16 text-right text-slate-500">size {sz}</span>
                      <div className="flex-1 h-4 bg-gray-200 dark:bg-slate-700 rounded overflow-hidden"><div className="h-full bg-indigo-500 rounded" style={{width:`${(cnt/mx)*100}%`}}/></div>
                      <span className="text-xs w-10 text-slate-500">{cnt}</span>
                    </div>
                  ));})()}
                </div>
              </>)}

              {/* L-Diversity */}
              <h3>Sensitive Attribute Exposure</h3>
              {sensitiveCandidates.length>0 ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <select className="border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm rounded px-3 py-2" value={sensCol} onChange={e=>setSensCol(e.target.value)}>
                      {sensitiveCandidates.map(c=><option key={c} value={c}>{c}</option>)}
                    </select>
                    <button className="btn-primary text-sm" onClick={loadLDiv} disabled={loadingLdiv||!sensCol}>{loadingLdiv?'Computing…':'Compute l-diversity'}</button>
                  </div>
                  {ldiv && (
                    <div className="space-y-3">
                      <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg p-4 inline-block">
                        <p className="text-xs text-gray-500">Min l-diversity for {ldiv.sensitive_attribute}</p>
                        <p className="text-3xl font-bold text-slate-800 dark:text-slate-200">{ldiv.min_l_diversity}</p>
                      </div>
                      {ldiv.details.length>0 && (
                        <div className="overflow-x-auto"><table className="data-table"><thead><tr>
                          {Object.keys(ldiv.details[0]).map(k=><th key={k}>{k}</th>)}
                        </tr></thead><tbody>
                          {ldiv.details.slice(0,10).map((r,i)=>(
                            <tr key={i}>{Object.values(r).map((v,j)=><td key={j}>{String(v)}</td>)}</tr>
                          ))}
                        </tbody></table></div>
                      )}
                    </div>
                  )}
                </div>
              ) : <p className="text-sm text-gray-500">No sensitive columns currently classified.</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
