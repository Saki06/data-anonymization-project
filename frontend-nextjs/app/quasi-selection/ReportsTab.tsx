'use client';
import { useState } from 'react';
import { API_BASE } from '@/lib/SessionContext';

interface RiskCombo { qi_cols: string; comb_size: number; k_min: number; unique_pct: number; total_groups: number; avg_group_size: number; max_group_size: number; unique_groups: number; risk_level: string; }
interface ClassDetail { column_name: string; class: string; confidence: number; reasons: string; }

export default function ReportsTab({
  sid, classDetails, riskCombos, datasetShape,
}: {
  sid: string;
  classDetails: ClassDetail[];
  riskCombos: RiskCombo[];
  datasetShape: [number, number];
}) {
  const [reportJson, setReportJson] = useState<any>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  const downloadCSV = (rows: Record<string,any>[], filename: string) => {
    if(!rows.length) return;
    const keys = Object.keys(rows[0]);
    const csv = [keys.join(','), ...rows.map(r=>keys.map(k=>JSON.stringify(r[k]??'')).join(','))].join('\n');
    const blob = new Blob([csv],{type:'text/csv'});
    const a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=filename; a.click();
  };

  const downloadTXT = (text: string, filename: string) => {
    const blob = new Blob([text],{type:'text/plain'});
    const a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=filename; a.click();
  };

  const loadFullReport = async () => {
    setLoadingReport(true);
    const fd = new FormData();
    fd.append('session_id', sid);
    try {
      const res = await fetch(`${API_BASE}/generate-report`,{method:'POST',body:fd});
      if(res.ok) setReportJson(await res.json());
    } catch{}
    finally{setLoadingReport(false);}
  };

  // Classification summary
  const classCounts: Record<string,number> = {};
  classDetails.forEach(d => { classCounts[d.class] = (classCounts[d.class]||0)+1; });

  // Build risk summary text
  const top = riskCombos.length ? riskCombos[0] : null;
  const riskSummaryText = top ? `SDC Privacy / Anonymization Tool - Risk Summary

Dataset rows: ${datasetShape[0]}
Dataset columns: ${datasetShape[1]}

Classification Summary:
${Object.entries(classCounts).map(([k,v])=>`${k}: ${v}`).join('\n')}

Highest Risk Combination:
QI Columns: ${top.qi_cols}
Minimum k-anonymity: ${top.k_min}
Unique Percentage: ${top.unique_pct}%
Risk Level: ${top.risk_level}
` : '';

  return (
    <div className="space-y-6">
      {/* Classification Results */}
      <div className="section">
        <h3>Attribute Classification Results</h3>
        {classDetails.length > 0 ? (
          <>
            <div className="overflow-x-auto">
              <table className="data-table"><thead><tr>
                <th>Column</th><th>Class</th><th>Confidence</th><th>Reasons</th>
              </tr></thead><tbody>
                {classDetails.map((d,i)=>(
                  <tr key={i}><td className="font-medium">{d.column_name}</td><td><span className="badge badge-info">{d.class}</span></td><td>{Math.round(d.confidence*100)}%</td><td className="text-xs">{d.reasons}</td></tr>
                ))}
              </tbody></table>
            </div>
            <button className="btn-primary mt-3" onClick={()=>downloadCSV(classDetails.map(d=>({column:d.column_name,class:d.class,confidence:d.confidence,reasons:d.reasons})),'classification_results.csv')}>
              📥 Download Classification CSV
            </button>
          </>
        ) : <p className="text-sm text-gray-500">Run auto-detection first to see classification results.</p>}
      </div>

      {/* Risk Results */}
      <div className="section">
        <h3>Risk Analysis Results</h3>
        {riskCombos.length > 0 ? (
          <>
            <div className="overflow-x-auto">
              <table className="data-table"><thead><tr>
                <th>QI Columns</th><th>Size</th><th>k-min</th><th>Unique %</th><th>Risk</th>
              </tr></thead><tbody>
                {riskCombos.map((c,i)=>(
                  <tr key={i}><td>{c.qi_cols}</td><td>{c.comb_size}</td><td>{c.k_min}</td><td>{c.unique_pct}%</td><td><span className="badge badge-warning">{c.risk_level}</span></td></tr>
                ))}
              </tbody></table>
            </div>
            <div className="flex gap-3 mt-3 flex-wrap">
              <button className="btn-primary" onClick={()=>downloadCSV(riskCombos,'risk_results.csv')}>📥 Download Risk Results CSV</button>
              <button className="btn-secondary" onClick={()=>downloadTXT(riskSummaryText,'risk_summary.txt')}>📥 Download Risk Summary TXT</button>
            </div>
          </>
        ) : <p className="text-sm text-gray-500">Run risk analysis first to export risk results.</p>}
      </div>

      {/* Full Report */}
      <div className="section">
        <h3>Full Classification Report (JSON)</h3>
        <button className="btn-info" onClick={loadFullReport} disabled={loadingReport}>
          {loadingReport ? 'Generating…' : '📄 Generate Full Report'}
        </button>
        {reportJson && (
          <div className="mt-3">
            <pre className="bg-slate-800 text-green-300 text-xs p-4 rounded-lg overflow-x-auto max-h-96">{JSON.stringify(reportJson,null,2)}</pre>
            <button className="btn-secondary mt-2" onClick={()=>downloadTXT(JSON.stringify(reportJson,null,2),'full_report.json')}>📥 Download JSON Report</button>
          </div>
        )}
      </div>
    </div>
  );
}
