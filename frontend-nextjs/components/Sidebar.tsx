'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ShieldAlert, Database, Lock, Search, FileCog, Home, LayoutDashboard } from 'lucide-react';

export default function Sidebar() {
  const pathname = usePathname();

  // No sidebar on the landing/home page
  if (pathname === '/') return null;

  const navItems = [
    { label: 'Home', path: '/', icon: Home },
    { label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { label: 'Quasi-Selection', path: '/quasi-selection', icon: FileCog },
    { label: 'Anonymization', path: '/anonymization', icon: Lock },
    { label: 'Synthetic Data', path: '/synthetic-data', icon: Database },
    { label: 'Risk Assessment', path: '/reidentification', icon: Search },
  ];

  return (
    <aside className="w-64 bg-slate-900 dark:bg-slate-950 border-r border-slate-800 text-slate-300 flex-col hidden md:flex shrink-0 h-screen sticky top-0">
      {/* Brand */}
      <div className="h-16 flex items-center px-6 border-b border-slate-800 bg-slate-950">
        <ShieldAlert className="w-6 h-6 text-blue-500 mr-3" />
        <span className="font-bold text-white text-sm tracking-wide uppercase">Anonymization System</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-6 px-3 space-y-1 overflow-y-auto">
        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 px-3">
          Main Menu
        </div>
        {navItems.map((item) => {
          const isActive = pathname === item.path;
          const Icon = item.icon;
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-600 font-semibold text-white'
                  : 'hover:bg-slate-800 hover:text-white'
              }`}
            >
              <Icon className={`w-5 h-5 ${isActive ? 'text-blue-200' : 'text-slate-400'}`} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="p-4 border-t border-slate-800 text-xs text-slate-500 bg-slate-950">
        <p className="mb-1">Version 1.0.0</p>
        <p>Authorized Use Only</p>
      </div>
    </aside>
  );
}
