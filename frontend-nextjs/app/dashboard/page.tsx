'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSession, API_BASE, DatasetInfo } from '@/lib/SessionContext';
import StatusBadge from '@/components/StatusBadge';
import DataTable from '@/components/DataTable';
import { LayoutDashboard, FileCog, Lock, Database, Search, UploadCloud, FileSpreadsheet } from 'lucide-react';

export default function HomePage() {
  const router = useRouter();
  const { sessionId, datasetInfo, setSession } = useSession();

  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Check backend on mount
  useEffect(() => {
    fetch(`${API_BASE}/`)
      .then((r) => setBackendStatus(r.ok ? 'connected' : 'disconnected'))
      .catch(() => setBackendStatus('disconnected'));
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setUploadError('');
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
      if (!res.ok) {
        const txt = await res.text();
        let msg = `Upload failed (${res.status})`;
        try { msg = JSON.parse(txt).detail || msg; } catch {}
        throw new Error(msg);
      }

      const raw = await res.json();
      // Normalise response
      if (!raw.shape && raw.sample_data?.length) {
        raw.shape = [raw.sample_data.length, Object.keys(raw.sample_data[0] || {}).length];
      }
      if (!raw.columns && raw.sample_data?.length) {
        raw.columns = Object.keys(raw.sample_data[0]);
      }

      const info: DatasetInfo = {
        session_id: raw.session_id,
        columns: raw.columns ?? [],
        shape: raw.shape ?? [0, 0],
        sample_data: raw.sample_data ?? [],
      };
      setSession(raw.session_id, info);
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const navigateTo = useCallback(
    (path: string) => {
      if (!sessionId) { alert('Please upload a dataset first'); return; }
      router.push(`${path}?session_id=${encodeURIComponent(sessionId)}`);
    },
    [sessionId, router]
  );

  const navItems = [
    { icon: FileCog, label: 'Quasi-Identifier Selection', desc: 'Select quasi-identifiers and sensitive attributes for anonymization', path: '/quasi-selection' },
    { icon: Lock, label: 'Anonymization', desc: 'Run risk analysis, get recommendations, and apply anonymization methods', path: '/anonymization' },
    { icon: Database, label: 'Synthetic Data', desc: 'Generate synthetic data that preserves statistical properties', path: '/synthetic-data' },
    { icon: Search, label: 'Re-identification Check', desc: 'Check your anonymized data for potential re-identification risks', path: '/reidentification' },
  ];

  return (
    <div className="page-container">
      {/* Page Title Area */}
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2.5 bg-blue-100 text-blue-700 rounded-lg">
          <LayoutDashboard className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 m-0 border-none pb-0">System Dashboard</h1>
          <p className="text-slate-500 text-sm mt-0.5 m-0 font-medium">Overview & Data Intake</p>
        </div>
      </div>

      {/* Backend Status */}
      <div className="mb-6">
        <StatusBadge
          status={backendStatus}
          message={
            backendStatus === 'checking'
              ? 'Checking backend connection…'
              : backendStatus === 'connected'
              ? '✓ Backend connected'
              : '✗ Backend not connected — Run: python run_server.py'
          }
        />
      </div>

      {/* Upload Section */}
      <div className="section">
        <h2 className="flex items-center gap-2 m-0 pb-3 border-b border-slate-100 text-lg">
          <UploadCloud className="w-5 h-5 text-blue-600" />
          Data Intake &amp; Upload
        </h2>

        <div
          className="upload-area mt-6 flex flex-col items-center justify-center p-12 border-2 border-dashed border-slate-300 rounded-xl bg-slate-50 hover:bg-blue-50/50 hover:border-blue-400 transition-colors cursor-pointer group"
          onClick={() => fileInputRef.current?.click()}
        >
          <div className="w-12 h-12 bg-white rounded-full shadow-sm flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
            <FileSpreadsheet className="w-6 h-6 text-slate-400 group-hover:text-blue-500 transition-colors" />
          </div>
          <p className="text-slate-600 font-medium m-0">Click to upload CSV or Excel file</p>
          <p className="text-slate-400 text-sm mt-1 mb-0">Drag and drop functionality coming soon</p>
          {file && <span className="text-blue-600 font-bold mt-4 block p-2 bg-blue-50 rounded-md shadow-sm border border-blue-100">{file.name}</span>}
        </div>

        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".csv,.xlsx,.xls"
          onChange={handleFileChange}
        />

        <button
          className="btn-primary mt-4"
          disabled={!file || uploading}
          onClick={handleUpload}
        >
          {uploading ? 'Uploading…' : 'Upload File'}
        </button>

        {uploadError && <div className="alert-error mt-3">{uploadError}</div>}
      </div>

      {/* Dataset Info (after upload) */}
      {datasetInfo && (
        <div className="section">
          <h2>📊 Dataset Information</h2>
          <div className="alert-success mb-3">✓ File uploaded successfully!</div>
          <p><strong>Session ID:</strong> {datasetInfo.session_id}</p>
          <p><strong>Records:</strong> {datasetInfo.shape[0]} &nbsp;|&nbsp; <strong>Columns:</strong> {datasetInfo.shape[1]}</p>
          <p><strong>Columns:</strong> {datasetInfo.columns.join(', ')}</p>

          {datasetInfo.sample_data.length > 0 && (
            <>
              <h3 className="mt-4">Data Preview</h3>
              <DataTable columns={datasetInfo.columns} rows={datasetInfo.sample_data} maxRows={5} />
            </>
          )}
        </div>
      )}

      {/* Component Navigation */}
      {datasetInfo && (
        <div className="section">
          <h2 className="flex items-center gap-2 m-0 pb-3 border-b border-slate-100 text-lg">
            <LayoutDashboard className="w-5 h-5 text-blue-600" />
            System Modules
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mt-6">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.path} className="nav-card py-8 flex flex-col items-center justify-center text-center group" onClick={() => navigateTo(item.path)}>
                  <div className="w-16 h-16 bg-slate-50 text-slate-400 group-hover:bg-blue-50 group-hover:text-blue-600 rounded-2xl flex items-center justify-center mb-5 transition-all outline outline-1 outline-slate-200 group-hover:outline-blue-200 shadow-sm">
                    <Icon className="w-8 h-8" />
                  </div>
                  <h3 className="text-lg font-bold text-slate-800 mb-2">{item.label}</h3>
                  <p className="text-sm text-slate-500 max-w-xs">{item.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Dashboard Footer Logic */}
      <div className="text-center mt-6 text-slate-500">
        <p className="text-sm">Powered by AI Agent, Expert System &amp; NSGA-II Optimization</p>
      </div>
    </div>
  );
}
