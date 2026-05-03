'use client';

import Link from 'next/link';
import { ShieldCheck, UploadCloud, ScanSearch, Lock, ShieldAlert } from 'lucide-react';

const steps = [
  {
    step: '01',
    icon: UploadCloud,
    title: 'Upload Dataset',
    desc: 'Upload your CSV or Excel file. The system creates a secure session and previews your data instantly.',
  },
  {
    step: '02',
    icon: ScanSearch,
    title: 'Classify Identifiers',
    desc: 'Auto-detect direct identifiers, quasi-identifiers, and sensitive attributes using rule-based AI.',
  },
  {
    step: '03',
    icon: Lock,
    title: 'Anonymize',
    desc: 'Apply NSGA-II optimized k-anonymity, l-diversity, and t-closeness with generalization hierarchies.',
  },
  {
    step: '04',
    icon: ShieldCheck,
    title: 'Assess Risk',
    desc: 'Run the ML re-identification pipeline with SHAP explainability and an LLM narrative report.',
  },
];

export default function HomePage() {
  return (
    <div className="min-h-[calc(100vh-8rem)] flex flex-col">

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-4 py-20">
        <div className="inline-flex items-center gap-2 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-xs font-semibold px-4 py-1.5 rounded-full mb-6 uppercase tracking-widest">
          <ShieldAlert className="w-4 h-4" />
          SLIIT Research Project
        </div>

        <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 dark:text-white leading-tight max-w-3xl">
          AI-Powered{' '}
          <span className="text-blue-600 dark:text-blue-400">Data Anonymization</span>{' '}
          &amp; Privacy Risk Platform
        </h1>

        <p className="mt-5 text-lg text-slate-500 dark:text-slate-400 max-w-2xl">
          Automate statistical disclosure control with an expert system, multi-objective optimization,
          and ML-based re-identification risk assessment.
        </p>

        <div className="mt-8 flex flex-wrap gap-4 justify-center">
          <Link
            href="/login"
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold px-7 py-3 rounded-lg shadow-lg shadow-blue-500/25 transition-all text-sm"
          >
            <UploadCloud className="w-4 h-4" />
            Sign In
          </Link>
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 font-semibold px-7 py-3 rounded-lg shadow transition-all text-sm"
          >
            Create Account
          </Link>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-16 px-4 bg-slate-50 dark:bg-slate-900/50 rounded-2xl mx-2 mb-6">
        <h2 className="text-2xl font-bold text-center text-slate-800 dark:text-white mb-10">
          How It Works
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto">
          {steps.map(({ step, icon: Icon, title, desc }) => (
            <div
              key={step}
              className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-6 flex flex-col gap-3 shadow-sm hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-blue-500 bg-blue-50 dark:bg-blue-900/40 px-2 py-0.5 rounded-full">
                  {step}
                </span>
                <Icon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="font-bold text-slate-800 dark:text-white text-sm">{title}</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="text-center py-6 text-xs text-slate-400 dark:text-slate-600">
        <p className="font-semibold text-slate-500 dark:text-slate-500">
          Sri Lanka Institute of Information Technology (SLIIT)
        </p>
        <p className="mt-1">Data Anonymization Automation System &mdash; Research Project &copy; {new Date().getFullYear()}</p>
      </footer>

    </div>
  );
}
