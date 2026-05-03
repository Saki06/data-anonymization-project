'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { AuthProvider, useAuth } from '@/lib/AuthContext';
import Sidebar from '@/components/Sidebar';
import ThemeToggle from '@/components/ThemeToggle';
import { Bell, LogOut, UserCircle, Loader2 } from 'lucide-react';

/** Pages that render their own full-screen layout (no sidebar/header). */
const PUBLIC_ROUTES = ['/', '/login', '/signup'];

function InnerShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isAuthenticated, isLoading } = useAuth();

  // Client-side route protection — redirect to /login if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated && !PUBLIC_ROUTES.includes(pathname)) {
      router.replace('/login');
    }
  }, [isLoading, isAuthenticated, pathname, router]);

  // Public pages — render children directly (no sidebar/header)
  if (PUBLIC_ROUTES.includes(pathname)) {
    return <>{children}</>;
  }

  // Loading state while checking auth
  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-slate-100 dark:bg-slate-950">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
          <p className="text-sm text-slate-500 font-medium">Loading...</p>
        </div>
      </div>
    );
  }

  // Not authenticated — show nothing while redirecting
  if (!isAuthenticated) {
    return null;
  }

  // Authenticated app layout — sidebar + header
  return (
    <div className="flex h-screen w-full">
      <Sidebar />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header */}
        <header className="h-16 bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between px-6 shrink-0 z-10">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500">
            <span className="hidden md:inline-block bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded uppercase tracking-wider font-bold">
              OFFICIAL
            </span>
            <span className="text-slate-400">|</span>
            Data Protection Platform
          </div>

          <div className="flex items-center gap-3 text-slate-500 dark:text-slate-400">
            <ThemeToggle />
            <button className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
              <Bell className="w-5 h-5" />
            </button>
            <div className="h-5 w-px bg-slate-200 dark:bg-slate-700" />

            {user ? (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold">
                    {user.name.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-300 hidden sm:inline">
                    {user.name}
                  </span>
                </div>
                <button
                  onClick={() => { logout(); router.push('/login'); }}
                  title="Sign out"
                  className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <UserCircle className="w-6 h-6" />
                <span className="text-sm font-medium hidden sm:inline">Guest</span>
              </div>
            )}
          </div>
        </header>

        {/* Main Scrollable Content */}
        <main className="flex-1 overflow-y-auto p-4 md:p-8 bg-slate-100 dark:bg-slate-950 relative">
          <div className="max-w-7xl mx-auto w-full">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

export default function AuthLayoutShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <InnerShell>{children}</InnerShell>
    </AuthProvider>
  );
}
