import type { Metadata } from 'next';
import './globals.css';
import { SessionProvider } from '@/lib/SessionContext';
import Sidebar from '@/components/Sidebar';
import ThemeProvider from '@/components/ThemeProvider';
import ThemeToggle from '@/components/ThemeToggle';
import { Bell, UserCircle } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Anonymization Automation System',
  description: 'AI-Powered Statistical Disclosure Control & Data Anonymization',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-slate-100 dark:bg-slate-950 text-slate-800 dark:text-slate-200 font-sans antialiased overflow-hidden">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <SessionProvider>
          <div className="flex h-screen w-full">
            {/* Sidebar (Left) */}
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
                  <div className="h-5 w-px bg-slate-200 dark:bg-slate-700"></div>
                  <button className="flex items-center gap-2 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
                    <UserCircle className="w-6 h-6" />
                    <span className="text-sm font-medium hidden sm:inline">Admin User</span>
                  </button>
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
        </SessionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
